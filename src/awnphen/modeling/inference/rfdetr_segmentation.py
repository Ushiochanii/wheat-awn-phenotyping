"""RF-DETR segmentation adapter for the canonical awn evidence contract.

The module intentionally does not import rfdetr at module import time.  A trained
RF-DETR model instance is injected by the caller, which keeps the main project
environment independent from the dedicated RF-DETR environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from awnphen.modeling.inference.instance_segmentation_adapter import (
    InstanceMaskPrediction,
)
from awnphen.phenotyping.detection.providers import sha256_file


@dataclass(slots=True)
class RFDETRSegmentationAdapter:
    """Normalize RF-DETR segmentation predictions to canonical awn/spikelet classes."""

    model: Any
    input_size: int = 624
    label_map: Mapping[int, int] = field(default_factory=lambda: {0: 0, 1: 1})
    checkpoint_path: Path | None = None

    def __post_init__(self) -> None:
        self.input_size = int(self.input_size)
        self.label_map = {
            int(source): int(target)
            for source, target in dict(self.label_map).items()
        }
        if self.input_size <= 0:
            raise ValueError("input_size must be positive")
        if any(target not in (0, 1) for target in self.label_map.values()):
            raise ValueError("label_map targets must use canonical classes 0/1")
        if self.checkpoint_path is not None:
            self.checkpoint_path = Path(self.checkpoint_path)
            if not self.checkpoint_path.is_file():
                raise FileNotFoundError(self.checkpoint_path)

    @property
    def architecture_name(self) -> str:
        return "RF-DETR Seg XLarge"

    @property
    def model_input_size(self) -> int:
        return self.input_size

    def provenance_payload(self) -> dict[str, Any]:
        try:
            rfdetr_version = metadata.version("rfdetr")
        except metadata.PackageNotFoundError:
            rfdetr_version = None

        payload: dict[str, Any] = {
            "implementation": "awnphen.rfdetr_segmentation_adapter_v1",
            "architecture": self.architecture_name,
            "rfdetr_version": rfdetr_version,
            "model_input_size": self.input_size,
            "label_map": {
                str(source): target
                for source, target in self.label_map.items()
            },
            "input_color": "BGR->RGB",
            "predict_include_source_image": False,
            "mask_coordinate_space": "original_input_tile",
        }
        if self.checkpoint_path is not None:
            payload["checkpoint"] = str(self.checkpoint_path)
            payload["checkpoint_sha256"] = sha256_file(self.checkpoint_path)
        return payload

    def predict_tile(
        self,
        image_bgr: np.ndarray,
        *,
        confidence: float,
    ) -> tuple[InstanceMaskPrediction, ...]:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("expected HxWx3 BGR image")

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        detections = self.model.predict(
            rgb,
            threshold=confidence,
            shape=(self.input_size, self.input_size),
            include_source_image=False,
        )

        xyxy = np.asarray(getattr(detections, "xyxy", np.empty((0, 4))), dtype=float)
        scores = np.asarray(
            getattr(detections, "confidence", np.empty((0,))),
            dtype=float,
        )
        class_ids = np.asarray(
            getattr(detections, "class_id", np.empty((0,), dtype=int)),
            dtype=int,
        )
        masks_raw = getattr(detections, "mask", None)

        count = len(scores)
        if len(xyxy) != count or len(class_ids) != count:
            raise RuntimeError("RF-DETR detection fields have inconsistent lengths")
        if masks_raw is None:
            if count:
                raise RuntimeError("RF-DETR segmentation output is missing masks")
            return ()

        masks = np.asarray(masks_raw)
        if len(masks) != count:
            raise RuntimeError("RF-DETR mask count does not match detections")

        expected_shape = tuple(int(value) for value in image_bgr.shape[:2])
        result: list[InstanceMaskPrediction] = []
        for box_xyxy, score, source_label, mask in zip(
            xyxy,
            scores,
            class_ids,
            masks,
        ):
            if float(score) < confidence:
                continue
            canonical_class = self.label_map.get(int(source_label))
            if canonical_class is None:
                continue

            mask_array = np.asarray(mask)
            if mask_array.shape != expected_shape:
                raise RuntimeError(
                    "RF-DETR mask is not in original tile coordinates: "
                    f"got {mask_array.shape}, expected {expected_shape}"
                )
            result.append(
                InstanceMaskPrediction(
                    class_id=canonical_class,
                    confidence=float(score),
                    mask=(mask_array > 0).astype(np.uint8),
                    box_xyxy=tuple(float(value) for value in box_xyxy),
                )
            )
        return tuple(result)


__all__ = ["RFDETRSegmentationAdapter"]
