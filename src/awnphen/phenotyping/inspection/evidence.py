"""Inspector views for canonical Phase 2 DetectionEvidence."""

from __future__ import annotations

from collections import Counter

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from awnphen.phenotyping.detection.acquisition import EvidenceAcquisitionResult
from awnphen.core.domain.physical import DetectionEvidence, EvidenceProvider
from .schema import (
    InspectorObject,
    InspectorPageState,
    InspectorStage,
    LayerSpec,
    PageImage,
    PolygonPrimitive,
)


def _polygon_primitive(polygon: Polygon) -> PolygonPrimitive:
    rings = [
        tuple((float(x), float(y)) for x, y in polygon.exterior.coords)
    ]
    rings.extend(
        tuple((float(x), float(y)) for x, y in interior.coords)
        for interior in polygon.interiors
    )
    return PolygonPrimitive(rings=tuple(rings))


def _geometry_primitives(
    geometry: BaseGeometry,
) -> tuple[PolygonPrimitive, ...]:
    if isinstance(geometry, Polygon):
        return (_polygon_primitive(geometry),)
    if isinstance(geometry, MultiPolygon):
        return tuple(_polygon_primitive(item) for item in geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        result = []
        for item in geometry.geoms:
            if item.is_empty:
                continue
            result.extend(_geometry_primitives(item))
        if result:
            return tuple(result)
    raise TypeError(
        "DetectionEvidence geometry must contain polygonal segmentation"
    )


def _layer_id(provider: EvidenceProvider, class_name: str) -> str:
    return f"evidence.{provider.value}.{class_name}"


def _layer_title(provider: EvidenceProvider, class_name: str) -> str:
    provider_label = (
        "Primary"
        if provider is EvidenceProvider.PRIMARY
        else "Supplementary"
    )
    class_label = "芒" if class_name == "awn" else "小穗"
    return f"{provider_label} Evidence · {class_label}"


def _layers(
    result: EvidenceAcquisitionResult,
) -> tuple[LayerSpec, ...]:
    combinations = sorted(
        {
            (item.provider, item.class_name)
            for item in result.evidence
        },
        key=lambda pair: (
            0 if pair[0] is EvidenceProvider.PRIMARY else 1,
            0 if pair[1] == "awn" else 1,
        ),
    )
    return tuple(
        LayerSpec(
            layer_id=_layer_id(provider, class_name),
            stage=InspectorStage.EVIDENCE,
            title=_layer_title(provider, class_name),
            description=(
                "原始模型观察；尚未执行 merge、dedupe 或 reconciliation。"
            ),
            default_visible=True,
            default_opacity=0.62,
            confidence_filterable=True,
            z_index=index,
            legend_key=f"evidence.{provider.value}.{class_name}",
        )
        for index, (provider, class_name) in enumerate(combinations, start=10)
    )


def _object(item: DetectionEvidence) -> InspectorObject:
    return InspectorObject(
        view_id=f"view_{item.evidence_id}",
        object_id=str(item.evidence_id),
        layer_id=_layer_id(item.provider, item.class_name),
        stage=InspectorStage.EVIDENCE,
        primitives=_geometry_primitives(item.geometry),
        label=f"{item.class_name} evidence",
        status="observed",
        confidence=item.confidence,
        style_key=f"evidence.{item.provider.value}.{item.class_name}",
        provenance_ids=tuple(
            record.provenance_id
            for record in item.provenance
        ),
        tags=("canonical_evidence",),
        metadata={
            "class_id": item.class_id,
            "class_name": item.class_name,
            "provider": item.provider.value,
            "source_tile_id": item.source_tile_id,
            "source_prediction_index": item.source_prediction_index,
            "source_component_index": item.source_component_index,
            "canonical_detection_evidence": True,
        },
    )


def build_evidence_inspector_state(
    result: EvidenceAcquisitionResult,
    *,
    image: PageImage,
) -> InspectorPageState:
    provenance_by_id = {}
    for item in result.evidence:
        for record in item.provenance:
            provenance_by_id[record.provenance_id] = record

    counts = Counter(
        f"{item.provider.value}.{item.class_name}"
        for item in result.evidence
    )
    return InspectorPageState(
        page_id=result.page_id,
        snapshot_id=result.snapshot_id,
        image=image,
        layers=_layers(result),
        objects=tuple(_object(item) for item in result.evidence),
        provenance=tuple(
            provenance_by_id[key]
            for key in sorted(provenance_by_id)
        ),
        metadata={
            "canonical_detection_evidence_available": True,
            "evidence_count": len(result.evidence),
            "evidence_counts": dict(sorted(counts.items())),
            "providers": [item.value for item in result.providers],
            "raw_observations_sha256": result.raw_observations_sha256,
        },
    )


__all__ = ["build_evidence_inspector_state"]
