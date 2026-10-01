"""Conservative planning for high-overlap awn evidence compaction.

Raw DetectionEvidence remains immutable. This module only builds a reversible
computational plan that can later be used by performance-oriented stages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from awnphen.core.domain.physical import DetectionEvidence
from awnphen.core.domain.physical_provenance import EvidenceId, SnapshotId


@dataclass(frozen=True, slots=True)
class DuplicateEvidenceCluster:
    representative_id: EvidenceId
    member_ids: tuple[EvidenceId, ...]
    union_geometry: BaseGeometry
    representative_confidence: float
    min_anchor_bidirectional_overlap: float
    min_union_bidirectional_overlap: float
    union_area_inflation: float


@dataclass(frozen=True, slots=True)
class EvidenceCompactionPlan:
    page_id: str
    snapshot_id: SnapshotId
    source_evidence_count: int
    target_class_name: str
    threshold: float
    clusters: tuple[DuplicateEvidenceCluster, ...]

    @property
    def collapsed_evidence_count(self) -> int:
        return sum(len(cluster.member_ids) - 1 for cluster in self.clusters)

    @property
    def active_evidence_count(self) -> int:
        return self.source_evidence_count - self.collapsed_evidence_count

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)


def _bidirectional_overlap(
    left: BaseGeometry,
    right: BaseGeometry,
) -> tuple[float, float, float]:
    if left.is_empty or right.is_empty:
        return 0.0, 0.0, 0.0
    intersection = left.intersection(right).area
    if intersection <= 0.0:
        return 0.0, 0.0, 0.0
    left_fraction = intersection / max(left.area, 1e-9)
    right_fraction = intersection / max(right.area, 1e-9)
    return float(left_fraction), float(right_fraction), float(min(left_fraction, right_fraction))


def plan_high_overlap_awn_compaction(
    evidence: Sequence[DetectionEvidence],
    *,
    min_bidirectional_overlap: float = 0.90,
) -> EvidenceCompactionPlan:
    """Plan conservative duplicate contraction without deleting raw evidence.

    A candidate may join a cluster only when it strongly overlaps both the
    fixed anchor geometry and the current cluster union in both directions.
    The proposed new union must also remain strongly covered by the anchor.
    This blocks ordinary containment and transitive A≈B≈C chain growth.
    """

    evidence = tuple(evidence)
    if not evidence:
        raise ValueError("compaction requires at least one DetectionEvidence")
    threshold = float(min_bidirectional_overlap)
    if not 0.5 < threshold <= 1.0:
        raise ValueError("min_bidirectional_overlap must be within (0.5, 1.0]")

    page_ids = {item.page_id for item in evidence}
    snapshot_ids = {str(item.snapshot_id) for item in evidence}
    if len(page_ids) != 1 or len(snapshot_ids) != 1:
        raise ValueError("all evidence must share one page and snapshot")

    target = [item for item in evidence if item.class_name == "awn"]
    if len(target) < 2:
        return EvidenceCompactionPlan(
            page_id=evidence[0].page_id,
            snapshot_id=evidence[0].snapshot_id,
            source_evidence_count=len(evidence),
            target_class_name="awn",
            threshold=threshold,
            clusters=(),
        )

    geometries = [item.geometry for item in target]
    tree = STRtree(geometries)
    order = sorted(
        range(len(target)),
        key=lambda index: (
            -target[index].confidence,
            -target[index].geometry.area,
            str(target[index].evidence_id),
        ),
    )
    available = set(range(len(target)))
    clusters: list[DuplicateEvidenceCluster] = []

    for anchor_index in order:
        if anchor_index not in available:
            continue
        anchor = target[anchor_index]
        anchor_geometry = anchor.geometry
        current_union = anchor_geometry
        member_indices = [anchor_index]
        anchor_min = 1.0
        union_min = 1.0

        candidate_indices = [
            int(value)
            for value in tree.query(anchor_geometry.envelope)
            if int(value) != anchor_index and int(value) in available
        ]
        candidate_indices.sort(
            key=lambda index: (
                -target[index].confidence,
                -target[index].geometry.area,
                str(target[index].evidence_id),
            )
        )

        for candidate_index in candidate_indices:
            candidate = target[candidate_index]
            _, _, anchor_overlap = _bidirectional_overlap(
                anchor_geometry,
                candidate.geometry,
            )
            if anchor_overlap < threshold:
                continue

            _, _, union_overlap = _bidirectional_overlap(
                current_union,
                candidate.geometry,
            )
            if union_overlap < threshold:
                continue

            proposed_union = unary_union((current_union, candidate.geometry))
            _, _, anchor_union_overlap = _bidirectional_overlap(
                anchor_geometry,
                proposed_union,
            )
            if anchor_union_overlap < threshold:
                continue

            current_union = proposed_union
            member_indices.append(candidate_index)
            anchor_min = min(anchor_min, anchor_overlap)
            union_min = min(union_min, union_overlap)

        if len(member_indices) < 2:
            continue

        for index in member_indices:
            available.discard(index)
        member_ids = tuple(
            sorted(
                (target[index].evidence_id for index in member_indices),
                key=str,
            )
        )
        clusters.append(
            DuplicateEvidenceCluster(
                representative_id=anchor.evidence_id,
                member_ids=member_ids,
                union_geometry=current_union,
                representative_confidence=float(anchor.confidence),
                min_anchor_bidirectional_overlap=float(anchor_min),
                min_union_bidirectional_overlap=float(union_min),
                union_area_inflation=float(
                    current_union.area / max(anchor_geometry.area, 1e-9)
                ),
            )
        )

    clusters.sort(key=lambda cluster: str(cluster.representative_id))
    return EvidenceCompactionPlan(
        page_id=evidence[0].page_id,
        snapshot_id=evidence[0].snapshot_id,
        source_evidence_count=len(evidence),
        target_class_name="awn",
        threshold=threshold,
        clusters=tuple(clusters),
    )


__all__ = [
    "DuplicateEvidenceCluster",
    "EvidenceCompactionPlan",
    "plan_high_overlap_awn_compaction",
]
