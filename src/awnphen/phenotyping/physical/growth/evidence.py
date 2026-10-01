"""Awn evidence preparation for Unified Growth v1."""
from __future__ import annotations

from awnphen.core.domain.physical import HypothesisStatus, InstanceHypothesis
from awnphen.phenotyping.detection.compaction import plan_high_overlap_awn_compaction
from .config import DEFAULT_UNIFIED_GROWTH_CONFIG

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG


def _build_compacted_awn_hypotheses(evidence):
    """Build reversible high-overlap awn hypotheses without global awn reconciliation."""
    awns = [item for item in evidence if item.class_name == "awn"]
    by_id = {str(item.evidence_id): item for item in awns}
    plan = plan_high_overlap_awn_compaction(
        evidence,
        min_bidirectional_overlap=_CONFIG.compaction_overlap,
    )
    hypotheses = []
    compacted_member_ids: set[str] = set()
    for cluster in plan.clusters:
        member_ids = tuple(cluster.member_ids)
        compacted_member_ids.update(str(value) for value in member_ids)
        representative = by_id[str(cluster.representative_id)]
        hypotheses.append(
            InstanceHypothesis.create(
                snapshot_id=representative.snapshot_id,
                page_id=representative.page_id,
                class_id=representative.class_id,
                class_name="awn",
                evidence_ids=member_ids,
                geometry=cluster.union_geometry,
                status=HypothesisStatus.FUSED,
            )
        )
    for item in awns:
        if str(item.evidence_id) in compacted_member_ids:
            continue
        hypotheses.append(
            InstanceHypothesis.create(
                snapshot_id=item.snapshot_id,
                page_id=item.page_id,
                class_id=item.class_id,
                class_name="awn",
                evidence_ids=(item.evidence_id,),
                geometry=item.geometry,
                status=HypothesisStatus.SINGLETON,
            )
        )
    hypotheses.sort(key=lambda item: str(item.hypothesis_id))
    return tuple(hypotheses), plan

__all__ = ["_build_compacted_awn_hypotheses"]
