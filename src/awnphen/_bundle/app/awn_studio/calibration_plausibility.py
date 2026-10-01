"""Physical plausibility policy for a proposed automatic calibration.

Detector inference lives in spikelet_scale_probe.py. This module only turns one
probe result plus mm/px into an interpretable biological sanity check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

try:
    from .spikelet_scale_probe import (
        DEFAULT_MIN_DETECTIONS,
        SpikeletScaleResult,
    )
except ImportError:  # direct script/service execution
    from spikelet_scale_probe import (
        DEFAULT_MIN_DETECTIONS,
        SpikeletScaleResult,
    )

# Empirical project reference from annotated spikelets under the normal 5 mm-grid
# acquisition. The hard band is deliberately wider than the typical range.
REFERENCE_TYPICAL_MIN_MM = 10.0
REFERENCE_TYPICAL_MAX_MM = 20.0
BLOCK_MIN_MM = 8.0
BLOCK_MAX_MM = 24.0


@dataclass(frozen=True)
class CalibrationPlausibility:
    adequate: bool | None
    reason: str
    spikelet_count: int
    median_long_side_px: float | None
    median_long_side_mm: float | None
    reference_typical_min_mm: float
    reference_typical_max_mm: float
    block_min_mm: float
    block_max_mm: float
    confidence_min: float

    def public(self) -> dict[str, Any]:
        return asdict(self)


def assess_calibration_plausibility(
    measured: SpikeletScaleResult,
    *,
    mm_per_px: float,
    min_detections: int = DEFAULT_MIN_DETECTIONS,
) -> CalibrationPlausibility:
    if not np.isfinite(mm_per_px) or mm_per_px <= 0:
        raise ValueError("mm_per_px must be positive")

    if (
        measured.spikelet_count < min_detections
        or measured.median_long_side_px is None
    ):
        return CalibrationPlausibility(
            adequate=None,
            reason="insufficient_high_confidence_spikelets",
            spikelet_count=measured.spikelet_count,
            median_long_side_px=measured.median_long_side_px,
            median_long_side_mm=None,
            reference_typical_min_mm=REFERENCE_TYPICAL_MIN_MM,
            reference_typical_max_mm=REFERENCE_TYPICAL_MAX_MM,
            block_min_mm=BLOCK_MIN_MM,
            block_max_mm=BLOCK_MAX_MM,
            confidence_min=measured.confidence_min,
        )

    median_mm = float(measured.median_long_side_px * mm_per_px)
    adequate = BLOCK_MIN_MM <= median_mm <= BLOCK_MAX_MM
    reason = "plausible" if adequate else (
        "spikelets_too_small_for_calibration"
        if median_mm < BLOCK_MIN_MM
        else "spikelets_too_large_for_calibration"
    )
    return CalibrationPlausibility(
        adequate=adequate,
        reason=reason,
        spikelet_count=measured.spikelet_count,
        median_long_side_px=measured.median_long_side_px,
        median_long_side_mm=median_mm,
        reference_typical_min_mm=REFERENCE_TYPICAL_MIN_MM,
        reference_typical_max_mm=REFERENCE_TYPICAL_MAX_MM,
        block_min_mm=BLOCK_MIN_MM,
        block_max_mm=BLOCK_MAX_MM,
        confidence_min=measured.confidence_min,
    )


__all__ = [
    "CalibrationPlausibility",
    "assess_calibration_plausibility",
]
