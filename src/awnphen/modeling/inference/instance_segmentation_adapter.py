"""Model-agnostic instance-segmentation adapter contract.

Architecture-specific libraries must stop at this boundary.  The rest of the awn
pipeline consumes canonical class IDs (0=awn, 1=spikelet), confidence scores, and
tile-coordinate raster masks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

import numpy as np


@dataclass(frozen=True, slots=True)
class InstanceMaskPrediction:
    """One architecture-normalized instance prediction for one input tile."""

    class_id: int
    confidence: float
    mask: np.ndarray
    box_xyxy: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        class_id = int(self.class_id)
        if class_id not in (0, 1):
            raise ValueError("canonical class_id must be 0=awn or 1=spikelet")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

        mask = np.asarray(self.mask)
        if mask.ndim != 2:
            raise ValueError("mask must be a two-dimensional tile-coordinate array")
        if mask.size == 0:
            raise ValueError("mask must not be empty")

        box_xyxy = self.box_xyxy
        if box_xyxy is not None:
            box_xyxy = tuple(float(value) for value in box_xyxy)
            if len(box_xyxy) != 4:
                raise ValueError("box_xyxy must contain four coordinates")

        object.__setattr__(self, "class_id", class_id)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "mask", mask)
        object.__setattr__(self, "box_xyxy", box_xyxy)


@runtime_checkable
class InstanceSegmentationAdapter(Protocol):
    """Minimal contract implemented by YOLO-external segmentation backends."""

    @property
    def architecture_name(self) -> str:
        ...

    @property
    def model_input_size(self) -> int | tuple[int, int] | None:
        ...

    def provenance_payload(self) -> dict[str, Any]:
        ...

    def predict_tile(
        self,
        image_bgr: np.ndarray,
        *,
        confidence: float,
    ) -> Sequence[InstanceMaskPrediction]:
        ...


__all__ = [
    "InstanceMaskPrediction",
    "InstanceSegmentationAdapter",
]
