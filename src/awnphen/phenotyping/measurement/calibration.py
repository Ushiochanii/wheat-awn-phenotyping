"""5 mm graph-paper calibration shared core.

This module contains the runtime calibration path only:
- blue/cyan grid signal extraction;
- projection peak detection;
- robust period estimation;
- strip-wise stability checks;
- resolution-normalized x/y calibration with QC.

It intentionally excludes validation regression, report generation, overlays, and CLI.
"""

from __future__ import annotations

import cv2
import numpy as np
from scipy.signal import find_peaks

from .path_length import GRID_MM

REFERENCE_WIDTH_PX = 3508
REFERENCE_HEIGHT_PX = 2480
REFERENCE_PERIOD_MIN_PX = 54.0
REFERENCE_PERIOD_MAX_PX = 64.0
MAX_NORMALIZED_XY_DISAGREEMENT_FRACTION = 0.05
MAX_STRIP_RANGE_PX = 3.0
MIN_X_PEAKS = 40
MIN_Y_PEAKS = 25
MAX_PAGE_SCALE_ANISOTROPY_FRACTION = 0.05


def blue_score(image_bgr):
    """Return the historical cyan/blue graph-paper response."""
    image = image_bgr.astype(np.float32)
    b, g, r = cv2.split(image)
    score = np.clip(
        (b - r) * 0.7 + (g - r) * 0.3,
        0.0,
        None,
    )
    score *= ((b + g + r) / 3.0 > 120.0)
    return score


def projection_peaks(signal):
    """Detect candidate grid lines in a one-dimensional projection."""
    smoothed = cv2.GaussianBlur(
        np.asarray(signal, np.float32).reshape(1, -1),
        (0, 0),
        2.0,
    ).ravel()
    prominence = max(
        0.3,
        float(np.percentile(smoothed, 75)) * 0.15,
    )
    peaks, props = find_peaks(
        smoothed,
        distance=40,
        prominence=prominence,
    )
    return peaks.astype(int), smoothed, props


def robust_grid_period(peaks):
    """Estimate one grid-cell period while allowing missed grid lines."""
    peaks = np.asarray(peaks, dtype=float)
    diffs = np.diff(peaks)

    preferred = diffs[(diffs >= 50) & (diffs <= 68)]
    initial = (
        float(np.median(preferred))
        if preferred.size
        else float(np.median(diffs))
    )

    cells = np.maximum(
        1,
        np.rint(diffs / initial).astype(int),
    )
    normalized = diffs / cells
    keep = np.abs(normalized - initial) <= max(
        5.0,
        initial * 0.12,
    )
    period = float(np.median(normalized[keep])) if np.any(keep) else initial

    cells = np.maximum(
        1,
        np.rint(diffs / period).astype(int),
    )
    normalized = diffs / cells
    keep = np.abs(normalized - period) <= max(
        4.0,
        period * 0.10,
    )
    period = float(np.median(normalized[keep])) if np.any(keep) else period

    lattice_index = [0]
    for n in cells:
        lattice_index.append(
            lattice_index[-1] + int(n)
        )

    k = np.asarray(lattice_index, dtype=float)
    coeff = np.polyfit(k, peaks, 1)
    fitted = np.polyval(coeff, k)
    residual = peaks - fitted

    return {
        "period_px": period,
        "fit_period_px": float(coeff[0]),
        "fit_offset_px": float(coeff[1]),
        "peak_count": int(len(peaks)),
        "grid_intervals_inferred": int(
            k[-1] - k[0]
        ),
        "normalized_gap_median_px": float(
            np.median(normalized)
        ),
        "normalized_gap_std_px": float(
            np.std(normalized)
        ),
        "normalized_gap_p95_abs_deviation_px": float(
            np.percentile(
                np.abs(normalized - period),
                95,
            )
        ),
        "lattice_residual_mean_px": float(
            np.mean(residual)
        ),
        "lattice_residual_median_abs_px": float(
            np.median(np.abs(residual))
        ),
        "lattice_residual_p95_abs_px": float(
            np.percentile(
                np.abs(residual),
                95,
            )
        ),
        "lattice_residual_max_abs_px": float(
            np.max(np.abs(residual))
        ),
        "peaks_px": peaks.astype(int).tolist(),
        "inferred_cell_steps": (
            cells.astype(int).tolist()
        ),
    }


def strip_periods(
    score,
    axis,
    strips=6,
):
    """Estimate period independently in page strips for stability QC."""
    height, width = score.shape
    extent = height if axis == "x" else width
    records = []

    for index in range(strips):
        start = round(index * extent / strips)
        end = round((index + 1) * extent / strips)

        if axis == "x":
            projection = score[start:end, :].mean(
                axis=0
            )
        else:
            projection = score[:, start:end].mean(
                axis=1
            )

        peaks, _, _ = projection_peaks(
            projection
        )
        calibration = robust_grid_period(
            peaks
        )
        records.append(
            {
                "strip": index,
                "start_px": start,
                "end_px": end,
                "period_px": calibration[
                    "period_px"
                ],
                "peak_count": calibration[
                    "peak_count"
                ],
                "normalized_gap_std_px": (
                    calibration[
                        "normalized_gap_std_px"
                    ]
                ),
            }
        )

    return records


def _period_axis(score, axis: str):
    projection = score.mean(
        axis=0 if axis == "x" else 1
    )
    peaks, _smoothed, _props = (
        projection_peaks(projection)
    )
    calibration = robust_grid_period(peaks)
    strips = strip_periods(score, axis)
    values = np.asarray(
        [
            row["period_px"]
            for row in strips
        ],
        dtype=float,
    )
    return calibration, strips, values


def calibrate_grid_v2(image_bgr):
    """Return source-pixel x/y grid periods and the frozen v2 QC record.

    Input must be a complete page from the same framing/orientation family as the
    development dataset. Pixel resolution may differ.
    """
    if (
        image_bgr is None
        or image_bgr.ndim != 3
    ):
        raise ValueError(
            "Expected a BGR full-page image"
        )

    height, width = image_bgr.shape[:2]
    scale_x = float(
        width / REFERENCE_WIDTH_PX
    )
    scale_y = float(
        height / REFERENCE_HEIGHT_PX
    )

    normalized = image_bgr
    if (
        width,
        height,
    ) != (
        REFERENCE_WIDTH_PX,
        REFERENCE_HEIGHT_PX,
    ):
        interpolation = (
            cv2.INTER_AREA
            if (
                width > REFERENCE_WIDTH_PX
                or height > REFERENCE_HEIGHT_PX
            )
            else cv2.INTER_LINEAR
        )
        normalized = cv2.resize(
            image_bgr,
            (
                REFERENCE_WIDTH_PX,
                REFERENCE_HEIGHT_PX,
            ),
            interpolation=interpolation,
        )

    score = blue_score(normalized)
    x_cal_norm, x_strips, x_values = (
        _period_axis(score, "x")
    )
    y_cal_norm, y_strips, y_values = (
        _period_axis(score, "y")
    )

    x_norm = float(
        x_cal_norm["period_px"]
    )
    y_norm = float(
        y_cal_norm["period_px"]
    )

    x_period_source = x_norm * scale_x
    y_period_source = y_norm * scale_y

    mean_norm = max(
        1e-9,
        (x_norm + y_norm) / 2.0,
    )
    xy_disagreement = (
        abs(x_norm - y_norm)
        / mean_norm
    )

    x_strip_range = float(
        np.ptp(x_values)
    )
    y_strip_range = float(
        np.ptp(y_values)
    )

    page_scale_anisotropy = (
        abs(scale_x - scale_y)
        / max(
            1e-9,
            (scale_x + scale_y) / 2.0,
        )
    )

    checks = {
        "x_period_in_reference_range": (
            REFERENCE_PERIOD_MIN_PX
            <= x_norm
            <= REFERENCE_PERIOD_MAX_PX
        ),
        "y_period_in_reference_range": (
            REFERENCE_PERIOD_MIN_PX
            <= y_norm
            <= REFERENCE_PERIOD_MAX_PX
        ),
        "normalized_xy_period_consistent": (
            xy_disagreement
            <= MAX_NORMALIZED_XY_DISAGREEMENT_FRACTION
        ),
        "x_strip_stable": (
            x_strip_range
            <= MAX_STRIP_RANGE_PX
        ),
        "y_strip_stable": (
            y_strip_range
            <= MAX_STRIP_RANGE_PX
        ),
        "x_peak_count_sufficient": (
            int(
                x_cal_norm["peak_count"]
            )
            >= MIN_X_PEAKS
        ),
        "y_peak_count_sufficient": (
            int(
                y_cal_norm["peak_count"]
            )
            >= MIN_Y_PEAKS
        ),
        "page_scale_isotropic": (
            page_scale_anisotropy
            <= MAX_PAGE_SCALE_ANISOTROPY_FRACTION
        ),
    }

    qc_reasons = [
        name
        for name, passed in checks.items()
        if not passed
    ]
    adequate = bool(
        all(checks.values())
    )

    x_cal = dict(x_cal_norm)
    y_cal = dict(y_cal_norm)

    x_cal[
        "normalized_reference_period_px"
    ] = x_norm
    y_cal[
        "normalized_reference_period_px"
    ] = y_norm

    x_cal["period_px"] = float(
        x_period_source
    )
    y_cal["period_px"] = float(
        y_period_source
    )

    x_cal[
        "source_scale_factor"
    ] = scale_x
    y_cal[
        "source_scale_factor"
    ] = scale_y

    qc = {
        "calibration_version": (
            "grid_calibration_v2_resolution_normalized"
        ),
        "grid_mm": GRID_MM,
        "input_width_px": int(width),
        "input_height_px": int(height),
        "reference_width_px": (
            REFERENCE_WIDTH_PX
        ),
        "reference_height_px": (
            REFERENCE_HEIGHT_PX
        ),
        "source_scale_x": scale_x,
        "source_scale_y": scale_y,
        "page_scale_anisotropy_fraction": (
            page_scale_anisotropy
        ),
        "x_period_normalized_px_per_5mm": (
            x_norm
        ),
        "y_period_normalized_px_per_5mm": (
            y_norm
        ),
        "x_period_px_per_5mm": float(
            x_period_source
        ),
        "y_period_px_per_5mm": float(
            y_period_source
        ),
        "normalized_xy_period_disagreement_fraction": float(
            xy_disagreement
        ),
        "x_strip_range_normalized_px": (
            x_strip_range
        ),
        "y_strip_range_normalized_px": (
            y_strip_range
        ),
        # Historical report compatibility aliases.
        "x_strip_range_px": x_strip_range,
        "y_strip_range_px": y_strip_range,
        "x_peak_count": int(
            x_cal_norm["peak_count"]
        ),
        "y_peak_count": int(
            y_cal_norm["peak_count"]
        ),
        "x_lattice_p95_abs_residual_normalized_px": float(
            x_cal_norm[
                "lattice_residual_p95_abs_px"
            ]
        ),
        "y_lattice_p95_abs_residual_normalized_px": float(
            y_cal_norm[
                "lattice_residual_p95_abs_px"
            ]
        ),
        "x_lattice_p95_abs_residual_px": float(
            x_cal_norm[
                "lattice_residual_p95_abs_px"
            ]
        ),
        "y_lattice_p95_abs_residual_px": float(
            y_cal_norm[
                "lattice_residual_p95_abs_px"
            ]
        ),
        "lattice_residual_role": (
            "diagnostic_only_not_hard_gate"
        ),
        "checks": checks,
        "qc_reasons": qc_reasons,
        "affine_scale_adequate": adequate,
    }

    return (
        x_cal,
        y_cal,
        qc,
        {
            "x": x_strips,
            "y": y_strips,
        },
    )


__all__ = [
    "GRID_MM",
    "REFERENCE_WIDTH_PX",
    "REFERENCE_HEIGHT_PX",
    "REFERENCE_PERIOD_MIN_PX",
    "REFERENCE_PERIOD_MAX_PX",
    "MAX_NORMALIZED_XY_DISAGREEMENT_FRACTION",
    "MAX_STRIP_RANGE_PX",
    "MIN_X_PEAKS",
    "MIN_Y_PEAKS",
    "MAX_PAGE_SCALE_ANISOTROPY_FRACTION",
    "blue_score",
    "projection_peaks",
    "robust_grid_period",
    "strip_periods",
    "calibrate_grid_v2",
]
