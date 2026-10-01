"""Pre-physical assembly of highly-overlapping awn hypotheses.

This stage repairs reconciliation splits where the same physical awn survives as
multiple hypothesis objects. It is deliberately conservative:
- at least one member must be ambiguous;
- geometry must overlap strongly;
- ambiguous hypotheses with multiple stable anchors are deferred;
- ambiguous-only merges require mutual best matches;
- no transitive graph-chain assembly is allowed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from awnphen.core.domain.physical import HypothesisStatus, InstanceHypothesis
from awnphen.core.domain.physical_provenance import OperationProvenance

AWN_PREMERGE_IMPLEMENTATION = "awnphen_next.awn_premerge_v1"


@dataclass(frozen=True, slots=True)
class AwnPremergeConfig:
    min_iou: float = 0.45
    min_overlap_min: float = 0.60
    max_axis_angle_deg: float = 25.0


@dataclass(frozen=True, slots=True)
class AwnAssemblyDecision:
    source_hypothesis_id: str
    anchor_hypothesis_id: str
    iou: float
    overlap_min: float
    axis_angle_deg: float
    mode: str


@dataclass(frozen=True, slots=True)
class AwnPremergeResult:
    hypotheses: tuple[InstanceHypothesis, ...]
    assemblies: tuple[AwnAssemblyDecision, ...]
    deferred_ambiguous_ids: tuple[str, ...]


def _principal_axis(geometry: BaseGeometry) -> np.ndarray:
    rect = geometry.minimum_rotated_rectangle
    pts = np.asarray(rect.exterior.coords[:-1], dtype=float)
    if len(pts) < 2:
        return np.asarray([1.0, 0.0])
    edges = []
    for index in range(len(pts)):
        vector = pts[(index + 1) % len(pts)] - pts[index]
        edges.append((float(np.linalg.norm(vector)), vector))
    length, vector = max(edges, key=lambda item: item[0])
    if length <= 1e-9:
        return np.asarray([1.0, 0.0])
    return vector / length


def _axis_angle_deg(left: BaseGeometry, right: BaseGeometry) -> float:
    dot = abs(float(np.dot(_principal_axis(left), _principal_axis(right))))
    return math.degrees(math.acos(max(0.0, min(1.0, dot))))


def _pair_metrics(left: BaseGeometry, right: BaseGeometry) -> tuple[float, float, float]:
    intersection = float(left.intersection(right).area)
    if intersection <= 0:
        return 0.0, 0.0, _axis_angle_deg(left, right)
    union = float(left.union(right).area)
    iou = intersection / max(union, 1e-9)
    overlap_min = intersection / max(min(float(left.area), float(right.area)), 1e-9)
    return iou, overlap_min, _axis_angle_deg(left, right)


def _rank(hypothesis: InstanceHypothesis) -> tuple[int, int, float, str]:
    # Stable/non-ambiguous hypotheses are preferred as physical anchors.
    stable = 1 if hypothesis.status is not HypothesisStatus.AMBIGUOUS else 0
    return (
        stable,
        len(hypothesis.evidence_ids),
        float(hypothesis.geometry.area),
        str(hypothesis.hypothesis_id),
    )


def assemble_awn_hypotheses(
    hypotheses: Sequence[InstanceHypothesis],
    *,
    config: AwnPremergeConfig = AwnPremergeConfig(),
) -> AwnPremergeResult:
    ordered = tuple(sorted(hypotheses, key=lambda item: str(item.hypothesis_id)))
    if not ordered:
        raise ValueError("awn premerge requires hypotheses")
    pages = {item.page_id for item in ordered}
    snapshots = {str(item.snapshot_id) for item in ordered}
    if len(pages) != 1 or len(snapshots) != 1:
        raise ValueError("awn premerge requires one page and one snapshot")

    awns = [item for item in ordered if item.class_name == "awn"]
    by_id = {str(item.hypothesis_id): item for item in awns}
    eligible: dict[str, list[tuple[float, str, float, float, float]]] = {
        str(item.hypothesis_id): [] for item in awns
    }

    for index, left in enumerate(awns):
        for right in awns[index + 1 :]:
            if (
                left.status is not HypothesisStatus.AMBIGUOUS
                and right.status is not HypothesisStatus.AMBIGUOUS
            ):
                continue
            if not left.geometry.intersects(right.geometry):
                continue
            iou, overlap_min, angle = _pair_metrics(left.geometry, right.geometry)
            if (
                iou < config.min_iou
                or overlap_min < config.min_overlap_min
                or angle > config.max_axis_angle_deg
            ):
                continue
            left_id = str(left.hypothesis_id)
            right_id = str(right.hypothesis_id)
            # Sort primarily by IoU, then overlap, then tighter angle.
            score = iou + 0.1 * overlap_min - 0.001 * angle
            eligible[left_id].append((score, right_id, iou, overlap_min, angle))
            eligible[right_id].append((score, left_id, iou, overlap_min, angle))

    for values in eligible.values():
        values.sort(key=lambda item: (-item[0], item[1]))

    assignments: dict[str, tuple[str, float, float, float, str]] = {}
    deferred: set[str] = set()

    # First: ambiguous -> exactly one stable anchor.
    for source in awns:
        source_id = str(source.hypothesis_id)
        if source.status is not HypothesisStatus.AMBIGUOUS:
            continue
        stable_neighbors = [
            item for item in eligible[source_id]
            if by_id[item[1]].status is not HypothesisStatus.AMBIGUOUS
        ]
        stable_ids = {item[1] for item in stable_neighbors}
        if len(stable_ids) == 1:
            best = stable_neighbors[0]
            assignments[source_id] = (
                best[1], best[2], best[3], best[4], "ambiguous_to_stable_anchor"
            )
        elif len(stable_ids) > 1:
            deferred.add(source_id)

    # Second: ambiguous-only mutual best pairs, only for still-unassigned items.
    locked_ambiguous: set[str] = set()
    for source in awns:
        source_id = str(source.hypothesis_id)
        if (
            source.status is not HypothesisStatus.AMBIGUOUS
            or source_id in assignments
            or source_id in deferred
            or source_id in locked_ambiguous
        ):
            continue
        ambiguous_neighbors = [
            item for item in eligible[source_id]
            if by_id[item[1]].status is HypothesisStatus.AMBIGUOUS
            and item[1] not in assignments
            and item[1] not in deferred
            and item[1] not in locked_ambiguous
        ]
        if not ambiguous_neighbors:
            continue
        best = ambiguous_neighbors[0]
        partner_id = best[1]
        partner_candidates = [
            item for item in eligible[partner_id]
            if by_id[item[1]].status is HypothesisStatus.AMBIGUOUS
            and item[1] not in assignments
            and item[1] not in deferred
            and item[1] not in locked_ambiguous
        ]
        if not partner_candidates or partner_candidates[0][1] != source_id:
            continue

        # Pick one stable identity anchor deterministically, but do not chain it.
        source_h = by_id[source_id]
        partner_h = by_id[partner_id]
        anchor, child = (
            (source_h, partner_h)
            if _rank(source_h) >= _rank(partner_h)
            else (partner_h, source_h)
        )
        anchor_id = str(anchor.hypothesis_id)
        child_id = str(child.hypothesis_id)
        pair = next(item for item in eligible[child_id] if item[1] == anchor_id)
        assignments[child_id] = (
            anchor_id, pair[2], pair[3], pair[4], "ambiguous_mutual_best_pair"
        )
        locked_ambiguous.update({source_id, partner_id})

    members_by_anchor: dict[str, list[InstanceHypothesis]] = {}
    decisions: list[AwnAssemblyDecision] = []
    for source_id, (anchor_id, iou, overlap_min, angle, mode) in sorted(assignments.items()):
        members_by_anchor.setdefault(anchor_id, []).append(by_id[source_id])
        decisions.append(
            AwnAssemblyDecision(
                source_hypothesis_id=source_id,
                anchor_hypothesis_id=anchor_id,
                iou=float(iou),
                overlap_min=float(overlap_min),
                axis_angle_deg=float(angle),
                mode=mode,
            )
        )

    absorbed_ids = set(assignments)
    output: list[InstanceHypothesis] = []
    for item in ordered:
        item_id = str(item.hypothesis_id)
        if item.class_name != "awn":
            output.append(item)
            continue
        if item_id in absorbed_ids:
            continue
        attached = members_by_anchor.get(item_id, ())
        if not attached:
            output.append(item)
            continue

        members = [item, *attached]
        evidence_ids = tuple(
            sorted(
                {evidence_id for member in members for evidence_id in member.evidence_ids},
                key=str,
            )
        )
        geometry = unary_union([member.geometry for member in members])
        merged = InstanceHypothesis.create(
            snapshot_id=item.snapshot_id,
            page_id=item.page_id,
            class_id=item.class_id,
            class_name=item.class_name,
            evidence_ids=evidence_ids,
            geometry=geometry,
            status=HypothesisStatus.FUSED,
        )
        provenance = OperationProvenance(
            operation="assemble_awn_hypotheses",
            implementation=AWN_PREMERGE_IMPLEMENTATION,
            input_ids=tuple(str(member.hypothesis_id) for member in members),
            output_id=str(merged.hypothesis_id),
            status="assembled",
            parameters={
                "min_iou": config.min_iou,
                "min_overlap_min": config.min_overlap_min,
                "max_axis_angle_deg": config.max_axis_angle_deg,
            },
            evidence={
                "anchor_hypothesis_id": item_id,
                "source_hypothesis_ids": [str(member.hypothesis_id) for member in attached],
            },
        )
        merged = InstanceHypothesis.create(
            snapshot_id=merged.snapshot_id,
            page_id=merged.page_id,
            class_id=merged.class_id,
            class_name=merged.class_name,
            evidence_ids=merged.evidence_ids,
            geometry=merged.geometry,
            status=merged.status,
            provenance=(provenance,),
        )
        output.append(merged)

    return AwnPremergeResult(
        hypotheses=tuple(sorted(output, key=lambda item: str(item.hypothesis_id))),
        assemblies=tuple(decisions),
        deferred_ambiguous_ids=tuple(sorted(deferred)),
    )


__all__ = [
    "AWN_PREMERGE_IMPLEMENTATION",
    "AwnAssemblyDecision",
    "AwnPremergeConfig",
    "AwnPremergeResult",
    "assemble_awn_hypotheses",
]
