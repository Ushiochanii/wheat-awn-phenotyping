"""Pipeline Inspector views for Phase 3 instance reconciliation."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from awnphen.phenotyping.detection.acquisition import EvidenceAcquisitionResult
from awnphen.core.domain.physical import HypothesisStatus
from awnphen.phenotyping.detection.reconciliation import (
    PairDecision,
    PairDecisionStatus,
    ReconciliationResult,
)
from .evidence import build_evidence_inspector_state
from .schema import (
    ConnectionPrimitive,
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
    raise TypeError("reconciliation geometry must contain polygonal masks")


def _pair_layer_id(status: PairDecisionStatus) -> str:
    return f"reconciliation.pair.{status.value}"


def _hypothesis_layer_id(class_name: str, status: HypothesisStatus) -> str:
    return f"reconciliation.hypothesis.{class_name}.{status.value}"


def _layers() -> tuple[LayerSpec, ...]:
    pair_layers = (
        LayerSpec(
            layer_id=_pair_layer_id(PairDecisionStatus.STRONG_DUPLICATE),
            stage=InspectorStage.RECONCILIATION,
            title="Strong duplicate pairs",
            description="强重复 pair；允许进入同一 evidence cluster。",
            default_visible=True,
            default_opacity=0.85,
            z_index=30,
            legend_key="reconciliation.strong_duplicate",
        ),
        LayerSpec(
            layer_id=_pair_layer_id(PairDecisionStatus.AMBIGUOUS),
            stage=InspectorStage.RECONCILIATION,
            title="Ambiguous pairs",
            description="证据不足以安全融合；双方继续保留。",
            default_visible=True,
            default_opacity=0.8,
            z_index=31,
            legend_key="reconciliation.ambiguous",
        ),
        LayerSpec(
            layer_id=_pair_layer_id(PairDecisionStatus.DISTINCT),
            stage=InspectorStage.RECONCILIATION,
            title="Distinct pairs",
            description="候选邻域内明确不应合并的 pair。",
            default_visible=False,
            default_opacity=0.55,
            z_index=32,
            legend_key="reconciliation.distinct",
        ),
    )
    hypothesis_layers = []
    z = 40
    for class_name, class_label in (("awn", "芒"), ("spikelet", "小穗")):
        for status, status_label in (
            (HypothesisStatus.FUSED, "Fused"),
            (HypothesisStatus.SINGLETON, "Singleton"),
            (HypothesisStatus.AMBIGUOUS, "Ambiguous"),
        ):
            hypothesis_layers.append(
                LayerSpec(
                    layer_id=_hypothesis_layer_id(class_name, status),
                    stage=InspectorStage.RECONCILIATION,
                    title=f"{class_label} hypothesis · {status_label}",
                    description=(
                        "InstanceHypothesis；identity 由 evidence membership 决定。"
                    ),
                    default_visible=(
                        status is not HypothesisStatus.SINGLETON
                    ),
                    default_opacity=0.48,
                    z_index=z,
                    legend_key=f"reconciliation.{status.value}.{class_name}",
                )
            )
            z += 1
    return pair_layers + tuple(hypothesis_layers)


def _pair_object(
    decision: PairDecision,
    evidence_by_id,
) -> InspectorObject:
    left = evidence_by_id[str(decision.left_evidence_id)]
    right = evidence_by_id[str(decision.right_evidence_id)]
    start = tuple(
        float(v) for v in left.geometry.representative_point().coords[0]
    )
    end = tuple(
        float(v) for v in right.geometry.representative_point().coords[0]
    )
    return InspectorObject(
        view_id=f"view_{decision.pair_id}",
        object_id=decision.pair_id,
        layer_id=_pair_layer_id(decision.status),
        stage=InspectorStage.RECONCILIATION,
        primitives=(
            ConnectionPrimitive(
                start=start,
                end=end,
                source_object_id=str(decision.left_evidence_id),
                target_object_id=str(decision.right_evidence_id),
            ),
        ),
        label=f"{decision.class_name} pair",
        status=decision.status.value,
        confidence=min(
            decision.features.confidence_min,
            decision.features.confidence_max,
        ),
        style_key=f"reconciliation.{decision.status.value}",
        source_object_ids=(
            str(decision.left_evidence_id),
            str(decision.right_evidence_id),
        ),
        provenance_ids=(decision.provenance.provenance_id,),
        tags=("reconciliation_pair", decision.status.value),
        metadata={
            "class_name": decision.class_name,
            "reason": decision.reason,
            "strength": decision.strength,
            **decision.features.to_dict(),
        },
    )


def _hypothesis_object(
    hypothesis,
    diagnostic,
    evidence_by_id,
) -> InspectorObject:
    confidences = [
        evidence_by_id[str(value)].confidence
        for value in hypothesis.evidence_ids
    ]
    return InspectorObject(
        view_id=f"view_{hypothesis.hypothesis_id}",
        object_id=str(hypothesis.hypothesis_id),
        layer_id=_hypothesis_layer_id(
            hypothesis.class_name, hypothesis.status
        ),
        stage=InspectorStage.RECONCILIATION,
        primitives=_geometry_primitives(hypothesis.geometry),
        label=f"{hypothesis.class_name} hypothesis",
        status=hypothesis.status.value,
        confidence=max(confidences) if confidences else None,
        style_key=(
            f"reconciliation.{hypothesis.status.value}."
            f"{hypothesis.class_name}"
        ),
        source_object_ids=tuple(
            str(value) for value in hypothesis.evidence_ids
        ),
        provenance_ids=tuple(
            item.provenance_id for item in hypothesis.provenance
        ),
        tags=("instance_hypothesis", hypothesis.status.value),
        metadata={
            "class_id": hypothesis.class_id,
            "class_name": hypothesis.class_name,
            "source_evidence_ids": [
                str(value) for value in hypothesis.evidence_ids
            ],
            "evidence_count": len(hypothesis.evidence_ids),
            **dict(diagnostic),
        },
    )


def _unique_provenance(records: Iterable):
    by_id = {}
    for record in records:
        by_id[record.provenance_id] = record
    return tuple(by_id[key] for key in sorted(by_id))


def build_reconciliation_inspector_state(
    evidence_result: EvidenceAcquisitionResult,
    reconciliation_result: ReconciliationResult,
    *,
    image: PageImage,
) -> InspectorPageState:
    if evidence_result.page_id != reconciliation_result.page_id:
        raise ValueError("evidence/reconciliation page mismatch")
    if evidence_result.snapshot_id != reconciliation_result.snapshot_id:
        raise ValueError("evidence/reconciliation snapshot mismatch")

    evidence_state = build_evidence_inspector_state(
        evidence_result,
        image=image,
    )
    evidence_by_id = {
        str(item.evidence_id): item
        for item in evidence_result.evidence
    }

    pair_objects = tuple(
        _pair_object(item, evidence_by_id)
        for item in reconciliation_result.pair_decisions
    )
    hypothesis_objects = tuple(
        _hypothesis_object(
            item,
            reconciliation_result.hypothesis_diagnostics[
                str(item.hypothesis_id)
            ],
            evidence_by_id,
        )
        for item in reconciliation_result.hypotheses
    )

    provenance = _unique_provenance(
        [
            *evidence_state.provenance,
            *(
                item.provenance
                for item in reconciliation_result.pair_decisions
            ),
            *(
                record
                for item in reconciliation_result.hypotheses
                for record in item.provenance
            ),
        ]
    )
    pair_counts = Counter(
        item.status.value
        for item in reconciliation_result.pair_decisions
    )
    hypothesis_counts = Counter(
        f"{item.class_name}.{item.status.value}"
        for item in reconciliation_result.hypotheses
    )

    return InspectorPageState(
        page_id=evidence_state.page_id,
        snapshot_id=evidence_state.snapshot_id,
        image=image,
        layers=tuple(evidence_state.layers) + _layers(),
        objects=(
            tuple(evidence_state.objects)
            + pair_objects
            + hypothesis_objects
        ),
        provenance=provenance,
        metadata={
            **dict(evidence_state.metadata),
            "reconciliation_available": True,
            "reconciliation_config_sha256": (
                reconciliation_result.config_sha256
            ),
            "pair_decision_counts": dict(sorted(pair_counts.items())),
            "hypothesis_counts": dict(sorted(hypothesis_counts.items())),
            "blocked_strong_pair_count": len(
                reconciliation_result.blocked_strong_pair_ids
            ),
            "source_evidence_count": len(
                reconciliation_result.source_evidence_ids
            ),
            "hypothesis_count": len(
                reconciliation_result.hypotheses
            ),
        },
    )


__all__ = ["build_reconciliation_inspector_state"]
