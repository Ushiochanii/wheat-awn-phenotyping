"""Pre-merge spikelet cleanup and fragment attachment.

This stage sits after reconciliation and before physical seeding. It preserves
DetectionEvidence, removes only structurally implausible spikelet hypotheses,
and collapses small attached fragments into one larger spikelet hypothesis.
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

SPIKELET_PREMERGE_IMPLEMENTATION = "awnphen_next.spikelet_premerge_v1"


@dataclass(frozen=True, slots=True)
class SpikeletPremergeConfig:
    # User-selected physical cleanup minimum; areas below 10 mm² are rejected.
    tiny_area_mm2: float = 10.0
    max_awn_overlap_fraction: float = 0.50
    max_fragment_gap_mm: float = 2.0
    max_fragment_area_ratio: float = 0.25
    max_axis_angle_deg: float = 20.0
    min_small_overlap: float = 0.50


@dataclass(frozen=True, slots=True)
class SpikeletFilterDecision:
    hypothesis_id: str
    reasons: tuple[str, ...]
    area_mm2: float
    awn_overlap_fraction: float


@dataclass(frozen=True, slots=True)
class SpikeletAttachment:
    small_hypothesis_id: str
    large_hypothesis_id: str
    gap_mm: float
    area_ratio: float
    axis_angle_deg: float
    overlap_small: float


@dataclass(frozen=True, slots=True)
class SpikeletPremergeResult:
    hypotheses: tuple[InstanceHypothesis, ...]
    filtered: tuple[SpikeletFilterDecision, ...]
    attachments: tuple[SpikeletAttachment, ...]


def _principal_axis(geometry: BaseGeometry) -> np.ndarray:
    rect = geometry.minimum_rotated_rectangle
    pts = np.asarray(rect.exterior.coords[:-1], dtype=float)
    if len(pts) < 2:
        return np.asarray([1.0, 0.0])
    edges = []
    for index in range(len(pts)):
        vector = pts[(index + 1) % len(pts)] - pts[index]
        edges.append((float(np.linalg.norm(vector)), vector))
    vector = max(edges, key=lambda item: item[0])[1]
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else np.asarray([1.0, 0.0])


def _axis_angle_deg(first: BaseGeometry, second: BaseGeometry) -> float:
    dot = abs(float(np.dot(_principal_axis(first), _principal_axis(second))))
    return math.degrees(math.acos(max(0.0, min(1.0, dot))))


def _overlap_small(first: BaseGeometry, second: BaseGeometry) -> float:
    return float(first.intersection(second).area / max(min(first.area, second.area), 1e-9))


def preprocess_spikelet_hypotheses(
    hypotheses: Sequence[InstanceHypothesis],
    *,
    x_period_px_5mm: float,
    y_period_px_5mm: float,
    config: SpikeletPremergeConfig = SpikeletPremergeConfig(),
    forced_attachments: Sequence[tuple[str, str]] = (),
) -> SpikeletPremergeResult:
    """Clean and attach spikelet hypotheses before physical seeding.

    Ambiguous hypotheses are preserved untouched. Awn hypotheses are never
    mutated. Tiny/awn-contaminated spikelet hypotheses are removed from the
    downstream hypothesis set but remain fully recoverable from reconciliation
    and immutable DetectionEvidence.
    """
    ordered = tuple(sorted(hypotheses, key=lambda item: str(item.hypothesis_id)))
    if not ordered:
        raise ValueError("spikelet premerge requires hypotheses")
    if x_period_px_5mm <= 0 or y_period_px_5mm <= 0:
        raise ValueError("calibration periods must be positive")

    page_ids = {item.page_id for item in ordered}
    snapshots = {str(item.snapshot_id) for item in ordered}
    if len(page_ids) != 1 or len(snapshots) != 1:
        raise ValueError("spikelet premerge requires one page and one snapshot")

    awn_geometries = [
        item.geometry
        for item in ordered
        if item.class_name == "awn" and item.status is not HypothesisStatus.AMBIGUOUS
    ]
    awn_union = unary_union(awn_geometries) if awn_geometries else unary_union([])

    candidates = [
        item
        for item in ordered
        if item.class_name == "spikelet" and item.status is not HypothesisStatus.AMBIGUOUS
    ]
    filtered: list[SpikeletFilterDecision] = []
    filtered_ids: set[str] = set()

    for item in candidates:
        area_mm2 = float(item.geometry.area) * 25.0 / (
            float(x_period_px_5mm) * float(y_period_px_5mm)
        )
        awn_overlap = (
            float(item.geometry.intersection(awn_union).area / max(item.geometry.area, 1e-9))
            if not awn_union.is_empty
            else 0.0
        )
        reasons: list[str] = []
        if area_mm2 < config.tiny_area_mm2:
            reasons.append("tiny_area")
        if awn_overlap >= config.max_awn_overlap_fraction:
            reasons.append("awn_overlap_contamination")
        if reasons:
            filtered_ids.add(str(item.hypothesis_id))
            filtered.append(
                SpikeletFilterDecision(
                    hypothesis_id=str(item.hypothesis_id),
                    reasons=tuple(reasons),
                    area_mm2=area_mm2,
                    awn_overlap_fraction=awn_overlap,
                )
            )

    retained = [item for item in candidates if str(item.hypothesis_id) not in filtered_ids]
    retained_by_id = {str(item.hypothesis_id): item for item in retained}
    forced_target_by_small = {
        str(small_id): str(large_id)
        for small_id, large_id in forced_attachments
        if str(small_id) in retained_by_id
        and str(large_id) in retained_by_id
        and str(small_id) != str(large_id)
    }
    forced_target_ids = set(forced_target_by_small.values())
    relations: dict[str, list[tuple[float, float, str, InstanceHypothesis, float, float, float]]] = {}
    mean_period = (float(x_period_px_5mm) + float(y_period_px_5mm)) / 2.0

    for small in retained:
        options = []
        for large in retained:
            if small.hypothesis_id == large.hypothesis_id or large.geometry.area <= small.geometry.area:
                continue
            ratio = float(small.geometry.area / max(large.geometry.area, 1e-9))
            if ratio > config.max_fragment_area_ratio:
                continue
            gap_mm = float(small.geometry.distance(large.geometry)) * 5.0 / mean_period
            if gap_mm > config.max_fragment_gap_mm:
                continue
            angle = _axis_angle_deg(small.geometry, large.geometry)
            overlap = _overlap_small(small.geometry, large.geometry)
            if not (angle <= config.max_axis_angle_deg or overlap >= config.min_small_overlap):
                continue
            options.append(
                (gap_mm, -float(large.geometry.area), str(large.hypothesis_id), large, ratio, angle, overlap)
            )
        relations[str(small.hypothesis_id)] = sorted(options, key=lambda item: item[:3])

    # A fragment candidate may not act as a core target. This prevents chain
    # bridges from collapsing multiple physical spikelets through intermediate junk.
    source_ids = {
        small_id for small_id, options in relations.items()
        if options and small_id not in forced_target_ids
    }
    core_ids = {
        str(item.hypothesis_id)
        for item in retained
        if str(item.hypothesis_id) not in source_ids
    }

    absorbed: set[str] = set()
    target_members: dict[str, list[InstanceHypothesis]] = {}
    attachments: list[SpikeletAttachment] = []
    forced_applied: set[str] = set()
    for small in retained:
        small_id = str(small.hypothesis_id)
        if small_id in forced_target_ids:
            continue

        forced_large_id = forced_target_by_small.get(small_id)
        if forced_large_id is not None:
            large = retained_by_id[forced_large_id]
            ratio = float(small.geometry.area / max(large.geometry.area, 1e-9))
            gap_mm = float(small.geometry.distance(large.geometry)) * 5.0 / mean_period
            angle = _axis_angle_deg(small.geometry, large.geometry)
            overlap = _overlap_small(small.geometry, large.geometry)
            large_id = forced_large_id
            forced_applied.add(small_id)
        else:
            core_options = [
                option for option in relations.get(small_id, ())
                if str(option[3].hypothesis_id) in core_ids
            ]
            if not core_options:
                continue
            gap_mm, _, large_id, large, ratio, angle, overlap = core_options[0]
        absorbed.add(small_id)
        target_members.setdefault(large_id, []).append(small)
        attachments.append(
            SpikeletAttachment(
                small_hypothesis_id=small_id,
                large_hypothesis_id=large_id,
                gap_mm=gap_mm,
                area_ratio=ratio,
                axis_angle_deg=angle,
                overlap_small=overlap,
            )
        )

    output: list[InstanceHypothesis] = []
    for item in ordered:
        item_id = str(item.hypothesis_id)
        if item.class_name != "spikelet" or item.status is HypothesisStatus.AMBIGUOUS:
            output.append(item)
            continue
        if item_id in filtered_ids or item_id in absorbed:
            continue

        members = [item, *target_members.get(item_id, ())]
        if len(members) == 1:
            output.append(item)
            continue

        evidence_ids = tuple(
            sorted({evidence_id for member in members for evidence_id in member.evidence_ids}, key=str)
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
            operation="attach_spikelet_fragments",
            implementation=SPIKELET_PREMERGE_IMPLEMENTATION,
            input_ids=tuple(str(member.hypothesis_id) for member in members),
            output_id=str(merged.hypothesis_id),
            status="attached",
            parameters={
                "tiny_area_mm2": config.tiny_area_mm2,
                "max_awn_overlap_fraction": config.max_awn_overlap_fraction,
                "max_fragment_gap_mm": config.max_fragment_gap_mm,
                "max_fragment_area_ratio": config.max_fragment_area_ratio,
                "max_axis_angle_deg": config.max_axis_angle_deg,
                "min_small_overlap": config.min_small_overlap,
            },
            evidence={
                "source_evidence_ids": [str(value) for value in evidence_ids],
                "forced_attachment_small_ids": sorted(
                    str(member.hypothesis_id)
                    for member in members
                    if str(member.hypothesis_id) in forced_applied
                ),
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

    return SpikeletPremergeResult(
        hypotheses=tuple(sorted(output, key=lambda item: str(item.hypothesis_id))),
        filtered=tuple(sorted(filtered, key=lambda item: item.hypothesis_id)),
        attachments=tuple(sorted(attachments, key=lambda item: item.small_hypothesis_id)),
    )


__all__ = [
    "SPIKELET_PREMERGE_IMPLEMENTATION",
    "SpikeletAttachment",
    "SpikeletFilterDecision",
    "SpikeletPremergeConfig",
    "SpikeletPremergeResult",
    "preprocess_spikelet_hypotheses",
]
