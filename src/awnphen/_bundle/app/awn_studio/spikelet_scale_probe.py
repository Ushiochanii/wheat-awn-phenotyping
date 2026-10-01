"""Lightweight spikelet-only scale probe for experiment input diagnostics.

One detector, one measurement contract. Downstream policies (resolution gating and
physical calibration plausibility) consume the returned statistics and do not
know how inference is implemented.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = Path(
    os.environ.get(
        "AWNPHEN_SCALE_PROBE_WEIGHTS",
        ROOT / "models" / "spikelet_scale_probe.pt",
    )
)

# Measured on the 11 native-resolution validation pages with this exact model
# (461 detections, conf >= 0.50, imgsz=416). GT median was 201.5 px.
REFERENCE_LONG_SIDE_PX = 198.08
DEFAULT_CONFIDENCE = 0.50
DEFAULT_IMGSZ = 416
DEFAULT_MIN_DETECTIONS = 3


@dataclass(frozen=True, slots=True)
class SpikeletScaleResult:
    spikelet_count: int
    median_long_side_px: float | None
    median_geom_px: float | None
    p10_long_side_px: float | None
    p90_long_side_px: float | None
    reference_long_side_px: float
    confidence_min: float
    imgsz: int

    @property
    def observed_ratio(self) -> float | None:
        if self.median_long_side_px is None or self.reference_long_side_px <= 0:
            return None
        return self.median_long_side_px / self.reference_long_side_px

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["observed_ratio"] = self.observed_ratio
        return data


class SpikeletScaleProbe:
    """Run the dedicated YOLO11n spikelet detector and summarize object scale."""

    def __init__(
        self,
        weights: str | Path = DEFAULT_WEIGHTS,
        *,
        device: int | str = 0,
        confidence: float = DEFAULT_CONFIDENCE,
        imgsz: int = DEFAULT_IMGSZ,
        reference_long_side_px: float = REFERENCE_LONG_SIDE_PX,
    ) -> None:
        self.weights = Path(weights)
        self.device = device
        self.confidence = float(confidence)
        self.imgsz = int(imgsz)
        self.reference_long_side_px = float(reference_long_side_px)
        self.model = YOLO(str(self.weights)) if self.weights.is_file() else None
        self._lock = Lock()

    def measure(self, image: np.ndarray) -> SpikeletScaleResult:
        if image is None or image.size == 0:
            raise ValueError("image must be a non-empty ndarray")

        if self.model is None:
            return SpikeletScaleResult(
                spikelet_count=0,
                median_long_side_px=None,
                median_geom_px=None,
                p10_long_side_px=None,
                p90_long_side_px=None,
                reference_long_side_px=self.reference_long_side_px,
                confidence_min=self.confidence,
                imgsz=self.imgsz,
            )

        # Ultralytics maps xyxy back to source-image coordinates, which is
        # exactly what the resolution policy needs.
        with self._lock:
            prediction = self.model.predict(
                image,
                imgsz=self.imgsz,
                conf=self.confidence,
                classes=[0],
                device=self.device,
                verbose=False,
            )[0]

        long_sides: list[float] = []
        geom_scales: list[float] = []
        if prediction.boxes is not None and len(prediction.boxes):
            boxes = prediction.boxes.xyxy.detach().cpu().numpy()
            for x1, y1, x2, y2 in boxes:
                width = max(0.0, float(x2 - x1))
                height = max(0.0, float(y2 - y1))
                if width <= 0 or height <= 0:
                    continue
                long_sides.append(max(width, height))
                geom_scales.append(float(np.sqrt(width * height)))

        if not long_sides:
            return SpikeletScaleResult(
                spikelet_count=0,
                median_long_side_px=None,
                median_geom_px=None,
                p10_long_side_px=None,
                p90_long_side_px=None,
                reference_long_side_px=self.reference_long_side_px,
                confidence_min=self.confidence,
                imgsz=self.imgsz,
            )

        long_arr = np.asarray(long_sides, dtype=np.float64)
        geom_arr = np.asarray(geom_scales, dtype=np.float64)
        return SpikeletScaleResult(
            spikelet_count=len(long_sides),
            median_long_side_px=float(np.median(long_arr)),
            median_geom_px=float(np.median(geom_arr)),
            p10_long_side_px=float(np.percentile(long_arr, 10)),
            p90_long_side_px=float(np.percentile(long_arr, 90)),
            reference_long_side_px=self.reference_long_side_px,
            confidence_min=self.confidence,
            imgsz=self.imgsz,
        )


__all__ = [
    "DEFAULT_MIN_DETECTIONS",
    "DEFAULT_WEIGHTS",
    "REFERENCE_LONG_SIDE_PX",
    "SpikeletScaleProbe",
    "SpikeletScaleResult",
]
