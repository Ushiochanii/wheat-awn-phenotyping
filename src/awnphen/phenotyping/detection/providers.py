"""Evidence providers for the Phase 2 Evidence layer.

Providers produce raw page-coordinate observations only. They must not merge,
deduplicate, stitch, reconstruct, or select representatives.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from shapely import Polygon, box, make_valid
from shapely.ops import unary_union

from .acquisition import RawDetectionObservation
from awnphen.core.domain.physical import EvidenceProvider


PRIMARY_PROVIDER_IMPLEMENTATION = "awnphen_next.primary_ultralytics_tiled_v1"


def sha256_file(path: str | Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _starts(length: int, size: int, stride: int) -> list[int]:
    if not 0 < stride <= size:
        raise ValueError("require 0 < stride <= tile_size")
    return sorted(
        set(
            [
                *range(0, max(1, length - size + 1), stride),
                max(0, length - size),
            ]
        )
    )


def tile_windows(
    width: int,
    height: int,
    *,
    tile_size: int,
    stride: int,
) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(
        (
            x,
            y,
            min(x + tile_size, width),
            min(y + tile_size, height),
        )
        for y in _starts(height, tile_size, stride)
        for x in _starts(width, tile_size, stride)
    )


def _polygonal_parts(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        result = []
        for item in geometry.geoms:
            result.extend(_polygonal_parts(item))
        return result
    return []


def _page_component_geometries_from_mask(
    mask,
    *,
    offset_x: int,
    offset_y: int,
    target_width: int,
    target_height: int,
):
    """Polygonize raster connected components without binding them together."""

    array = np.asarray(mask, dtype=np.float32)
    if array.shape != (target_height, target_width):
        array = cv2.resize(
            array,
            (target_width, target_height),
            interpolation=cv2.INTER_NEAREST,
        )
    binary = np.ascontiguousarray((array > 0.5).astype(np.uint8))
    if not binary.any():
        return ()

    contours = cv2.findContours(
        binary,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )[0]

    components = []
    for contour in contours:
        points = contour.reshape(-1, 2)
        if len(points) >= 3:
            ring = (
                points.astype(float)
                + np.asarray([offset_x, offset_y], dtype=float)
            )
            parts = [
                item
                for item in _polygonal_parts(make_valid(Polygon(ring)))
                if not item.is_empty and item.area > 0
            ]
            if parts:
                geometry = unary_union(parts)
                if not geometry.is_empty:
                    components.append(geometry)
            continue

        # Preserve tiny 1-2 pixel islands rather than silently dropping them.
        x, y, width, height = cv2.boundingRect(contour)
        components.append(
            box(
                offset_x + x,
                offset_y + y,
                offset_x + x + max(1, width),
                offset_y + y + max(1, height),
            )
        )

    components = [
        item for item in components if not item.is_empty and item.area > 0
    ]
    components.sort(
        key=lambda item: (
            -float(item.area),
            tuple(float(value) for value in item.bounds),
        )
    )
    return tuple(components)


@dataclass(slots=True)
class PrimaryEvidenceProvider:
    """Current primary tiled Ultralytics segmentation provider."""

    model: Any
    page_dir: Path
    weights_path: Path
    tile_size: int = 640
    stride: int = 320
    model_imgsz: int | None = None
    confidence: float = 0.25
    nms_iou: float = 0.7
    device: int | str = 0

    def __post_init__(self) -> None:
        self.page_dir = Path(self.page_dir)
        self.weights_path = Path(self.weights_path)
        self.tile_size = int(self.tile_size)
        self.stride = int(self.stride)
        self.model_imgsz = (
            self.tile_size
            if self.model_imgsz is None
            else int(self.model_imgsz)
        )
        self.confidence = float(self.confidence)
        self.nms_iou = float(self.nms_iou)
        if self.tile_size <= 0:
            raise ValueError("tile_size must be positive")
        if not 0 < self.stride <= self.tile_size:
            raise ValueError("require 0 < stride <= tile_size")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not 0.0 <= self.nms_iou <= 1.0:
            raise ValueError("nms_iou must be within [0, 1]")
        if not self.weights_path.is_file():
            raise FileNotFoundError(self.weights_path)

    @property
    def provider(self) -> EvidenceProvider:
        return EvidenceProvider.PRIMARY

    def page_path(self, page_id: str) -> Path:
        return self.page_dir / f"{page_id}.png"

    def provenance_payload(self) -> dict[str, Any]:
        return {
            "implementation": PRIMARY_PROVIDER_IMPLEMENTATION,
            "model_identity": str(self.weights_path),
            "weights_sha256": sha256_file(self.weights_path),
            "tile_size": self.tile_size,
            "stride": self.stride,
            "model_imgsz": self.model_imgsz,
            "confidence": self.confidence,
            "nms_iou": self.nms_iou,
            "device": str(self.device),
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
        tiles = tile_windows(
            width,
            height,
            tile_size=self.tile_size,
            stride=self.stride,
        )
        observations: list[RawDetectionObservation] = []

        for tile_index, rect in enumerate(tiles):
            x1, y1, x2, y2 = rect
            crop = image[y1:y2, x1:x2]
            result = self.model.predict(
                crop,
                imgsz=self.model_imgsz,
                conf=self.confidence,
                iou=self.nms_iou,
                device=self.device,
                verbose=False,
            )[0]
            if result.masks is None:
                continue

            mask_data = result.masks.data
            if hasattr(mask_data, "cpu"):
                mask_data = mask_data.cpu().numpy()
            else:
                mask_data = np.asarray(mask_data)

            records = zip(
                mask_data,
                result.boxes.cls.cpu(),
                result.boxes.conf.cpu(),
                result.boxes.xyxy.cpu().numpy(),
            )
            crop_height, crop_width = crop.shape[:2]
            for source_prediction_index, (
                mask,
                class_id,
                confidence,
                bounds,
            ) in enumerate(records):
                component_geometries = _page_component_geometries_from_mask(
                    mask,
                    offset_x=x1,
                    offset_y=y1,
                    target_width=crop_width,
                    target_height=crop_height,
                )
                if not component_geometries:
                    continue

                page_box = (
                    np.asarray(bounds, dtype=float)
                    + np.asarray([x1, y1, x1, y1], dtype=float)
                )
                class_id_int = int(class_id)
                class_name = (
                    "awn"
                    if class_id_int == 0
                    else "spikelet"
                    if class_id_int == 1
                    else None
                )
                if class_name is None:
                    raise ValueError(
                        f"unsupported model class_id: {class_id_int}"
                    )

                for source_component_index, geometry in enumerate(
                    component_geometries
                ):
                    observations.append(
                        RawDetectionObservation(
                            class_id=class_id_int,
                            class_name=class_name,
                            confidence=float(confidence),
                            geometry=geometry,
                            source_tile_id=f"tile_{tile_index:04d}",
                            source_prediction_index=source_prediction_index,
                            source_component_index=source_component_index,
                            tile_xyxy=tuple(float(v) for v in rect),
                            box_xyxy=tuple(float(v) for v in page_box),
                        )
                    )

        return tuple(observations)


__all__ = [
    "PRIMARY_PROVIDER_IMPLEMENTATION",
    "PrimaryEvidenceProvider",
    "sha256_file",
    "tile_windows",
]
