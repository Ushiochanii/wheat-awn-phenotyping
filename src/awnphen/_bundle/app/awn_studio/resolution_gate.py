"""Experiment-only input resolution gate backed by SpikeletScaleProbe.

Policy:
- <30% of reference spikelet pixel scale: block by default; caller may force.
- 30-50%: automatically upscale to the reference scale.
- 50-200%: pass through unchanged.
- >200%: automatically downscale to 130% of the reference scale.
- Low-resolution decisions require at least 3 reliable spikelets.
- Overscale protection may trigger from 1 reliable spikelet.

No page-shape heuristic is used. Full pages and cell crops are judged from the
same detector-space statistic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np

try:
    from .spikelet_scale_probe import (
        DEFAULT_MIN_DETECTIONS,
        SpikeletScaleProbe,
    )
except ImportError:  # direct script/service execution
    from spikelet_scale_probe import (
        DEFAULT_MIN_DETECTIONS,
        SpikeletScaleProbe,
    )

DEFAULT_REJECT_RATIO = 0.30
DEFAULT_TRIGGER_RATIO = 0.50
DEFAULT_OVERSCALE_RATIO = 2.00
DEFAULT_OVERSCALE_TARGET_RATIO = 1.30


@dataclass(frozen=True, slots=True)
class ResolutionGateResult:
    status: str
    action: str
    applied: bool
    forced: bool
    scale_factor: float
    measurement_basis: str
    observed_spikelet_px: float | None
    reference_spikelet_px: float
    observed_ratio: float | None
    reject_ratio: float
    trigger_ratio: float
    overscale_ratio: float
    overscale_target_ratio: float
    spikelet_count: int
    input_width: int
    input_height: int
    output_width: int
    output_height: int

    def public(self) -> dict[str, Any]:
        return asdict(self)


class ResolutionGate:
    """Classify and optionally upscale one imported image."""

    def __init__(
        self,
        probe: SpikeletScaleProbe,
        *,
        reject_ratio: float = DEFAULT_REJECT_RATIO,
        trigger_ratio: float = DEFAULT_TRIGGER_RATIO,
        overscale_ratio: float = DEFAULT_OVERSCALE_RATIO,
        overscale_target_ratio: float = DEFAULT_OVERSCALE_TARGET_RATIO,
        min_detections: int = DEFAULT_MIN_DETECTIONS,
    ) -> None:
        if not 0 < reject_ratio < trigger_ratio <= 1:
            raise ValueError("resolution ratios must satisfy 0 < reject < trigger <= 1")
        if not 1 < overscale_target_ratio < overscale_ratio:
            raise ValueError("overscale ratios must satisfy 1 < target < trigger")
        self.probe = probe
        self.reject_ratio = float(reject_ratio)
        self.trigger_ratio = float(trigger_ratio)
        self.overscale_ratio = float(overscale_ratio)
        self.overscale_target_ratio = float(overscale_target_ratio)
        self.min_detections = int(min_detections)

    def prepare(
        self,
        image: np.ndarray,
        *,
        force_below_reject: bool = False,
    ) -> tuple[np.ndarray, ResolutionGateResult]:
        if image is None or image.size == 0:
            raise ValueError("image must be a non-empty ndarray")

        height, width = image.shape[:2]
        measured = self.probe.measure(image)
        count = measured.spikelet_count
        observed = measured.median_long_side_px
        raw_ratio = measured.observed_ratio
        ratio = raw_ratio if count >= self.min_detections else None
        overscale_ratio = raw_ratio if count >= 1 else None
        basis = "spikelet_scale_probe_yolo11n"

        def result(
            *,
            status: str,
            action: str,
            applied: bool,
            forced: bool,
            scale_factor: float,
            output_width: int,
            output_height: int,
            observed_ratio_value: float | None = None,
        ) -> ResolutionGateResult:
            return ResolutionGateResult(
                status=status,
                action=action,
                applied=applied,
                forced=forced,
                scale_factor=scale_factor,
                measurement_basis=basis,
                observed_spikelet_px=observed,
                reference_spikelet_px=measured.reference_long_side_px,
                observed_ratio=(
                    ratio if observed_ratio_value is None else observed_ratio_value
                ),
                reject_ratio=self.reject_ratio,
                trigger_ratio=self.trigger_ratio,
                overscale_ratio=self.overscale_ratio,
                overscale_target_ratio=self.overscale_target_ratio,
                spikelet_count=count,
                input_width=width,
                input_height=height,
                output_width=output_width,
                output_height=output_height,
            )

        boundary_epsilon = 0.001
        oversized = (
            overscale_ratio is not None
            and overscale_ratio > self.overscale_ratio + boundary_epsilon
        )
        if oversized:
            scale = self.overscale_target_ratio / max(overscale_ratio, 1e-6)
            out_width = max(1, int(round(width * scale)))
            out_height = max(1, int(round(height * scale)))
            prepared = cv2.resize(
                image,
                (out_width, out_height),
                interpolation=cv2.INTER_AREA,
            )
            return prepared, result(
                status="overscale",
                action="downscaled",
                applied=True,
                forced=False,
                scale_factor=scale,
                output_width=out_width,
                output_height=out_height,
                observed_ratio_value=overscale_ratio,
            )

        if ratio is None:
            return image.copy(), result(
                status="unassessed",
                action="pass_through",
                applied=False,
                forced=False,
                scale_factor=1.0,
                output_width=width,
                output_height=height,
            )

        too_low = ratio < self.reject_ratio - boundary_epsilon
        low = ratio < self.trigger_ratio - boundary_epsilon

        if too_low and not force_below_reject:
            return image.copy(), result(
                status="too_low",
                action="blocked",
                applied=False,
                forced=False,
                scale_factor=1.0,
                output_width=width,
                output_height=height,
            )

        if not low:
            return image.copy(), result(
                status="sufficient",
                action="pass_through",
                applied=False,
                forced=False,
                scale_factor=1.0,
                output_width=width,
                output_height=height,
            )

        scale = 1.0 / max(ratio, 1e-6)
        out_width = max(1, int(round(width * scale)))
        out_height = max(1, int(round(height * scale)))
        enhanced = cv2.resize(
            image,
            (out_width, out_height),
            interpolation=cv2.INTER_LANCZOS4,
        )
        return enhanced, result(
            status="forced_low" if too_low else "low",
            action="upscaled",
            applied=True,
            forced=bool(too_low and force_below_reject),
            scale_factor=scale,
            output_width=out_width,
            output_height=out_height,
        )


__all__ = [
    "DEFAULT_REJECT_RATIO",
    "DEFAULT_TRIGGER_RATIO",
    "DEFAULT_OVERSCALE_RATIO",
    "DEFAULT_OVERSCALE_TARGET_RATIO",
    "ResolutionGate",
    "ResolutionGateResult",
]
