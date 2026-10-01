"""Tiled canonical Evidence provider backed by an instance-segmentation adapter.

This provider is the common bridge used by non-Ultralytics architectures.  All
architecture-specific code stays inside the adapter; the provider is responsible only
for common page tiling, coordinate restoration, component splitting, and canonical
RawDetectionObservation creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from awnphen.core.domain.physical import EvidenceProvider
from awnphen.modeling.inference.instance_segmentation_adapter import (
    InstanceSegmentationAdapter,
)
from awnphen.phenotyping.detection.acquisition import RawDetectionObservation
from awnphen.phenotyping.detection.providers import (
    _page_component_geometries_from_mask,
    tile_windows,
)


ADAPTER_PROVIDER_IMPLEMENTATION = "awnphen.adapter_tiled_instance_segmentation_v1"


@dataclass(slots=True)
class AdapterEvidenceProvider:
    """Common whole-page tiled provider for cross-architecture models."""

    adapter: InstanceSegmentationAdapter
    page_dir: Path
    tile_size: int = 640
    stride: int = 320
    confidence: float = 0.05

    def __post_init__(self) -> None:
        self.page_dir = Path(self.page_dir)
        self.tile_size = int(self.tile_size)
        self.stride = int(self.stride)
        self.confidence = float(self.confidence)
        if self.tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if not 0 < self.stride <= self.tile_size:
            raise ValueError("require 0 < stride <= tile_size")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    @property
    def provider(self) -> EvidenceProvider:
        return EvidenceProvider.PRIMARY

    def page_path(self, page_id: str) -> Path:
        return self.page_dir / f"{page_id}.png"

    def provenance_payload(self) -> dict[str, Any]:
        adapter_payload = dict(self.adapter.provenance_payload())
        weights_sha256 = str(adapter_payload.get("checkpoint_sha256") or "").strip()
        if not weights_sha256:
            raise ValueError(
                "adapter provenance must provide checkpoint_sha256 so canonical "
                "evidence can record immutable model weights"
            )
        return {
            "implementation": ADAPTER_PROVIDER_IMPLEMENTATION,
            "model_identity": self.adapter.architecture_name,
            "weights_sha256": weights_sha256,
            "architecture_name": self.adapter.architecture_name,
            "adapter": adapter_payload,
            "tile_size": self.tile_size,
            "stride": self.stride,
            "model_imgsz": self.adapter.model_input_size,
            "confidence": self.confidence,
            "coordinate_space": "page_px",
            "mask_component_policy": "split_disconnected_raster_components",
            "component_order": "area_desc_then_bounds",
        }

    def observe_page(
        self,
        *,
        page_id: str,
    ) -> tuple[RawDetectionObservation, ...]:
        source = self.page_path(page_id)
        image = cv2.imread(str(source))
        if image is None:
            raise FileNotFoundError(source)

        height, width = image.shape[:2]
        windows = tile_windows(
            width,
            height,
            tile_size=self.tile_size,
            stride=self.stride,
        )
        observations: list[RawDetectionObservation] = []

        for tile_index, rect in enumerate(windows):
            x1, y1, x2, y2 = rect
            crop = image[y1:y2, x1:x2]
            crop_height, crop_width = crop.shape[:2]

            predictions = self.adapter.predict_tile(
                crop,
                confidence=self.confidence,
            )
            for source_prediction_index, prediction in enumerate(predictions):
                component_geometries = _page_component_geometries_from_mask(
                    prediction.mask,
                    offset_x=x1,
                    offset_y=y1,
                    target_width=crop_width,
                    target_height=crop_height,
                )
                if not component_geometries:
                    continue

                page_box = None
                if prediction.box_xyxy is not None:
                    page_box = (
                        np.asarray(prediction.box_xyxy, dtype=float)
                        + np.asarray([x1, y1, x1, y1], dtype=float)
                    )

                class_name = "awn" if prediction.class_id == 0 else "spikelet"
                for source_component_index, geometry in enumerate(
                    component_geometries
                ):
                    observations.append(
                        RawDetectionObservation(
                            class_id=prediction.class_id,
                            class_name=class_name,
                            confidence=prediction.confidence,
                            geometry=geometry,
                            source_tile_id=f"tile_{tile_index:04d}",
                            source_prediction_index=source_prediction_index,
                            source_component_index=source_component_index,
                            tile_xyxy=tuple(float(value) for value in rect),
                            box_xyxy=(
                                None
                                if page_box is None
                                else tuple(float(value) for value in page_box)
                            ),
                        )
                    )

        return tuple(observations)


__all__ = [
    "ADAPTER_PROVIDER_IMPLEMENTATION",
    "AdapterEvidenceProvider",
]
