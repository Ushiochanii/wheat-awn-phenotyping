"""Shared support-path resolution for physical awn trajectories.

This is the small, side-effect-free integration kernel used by Unified Growth.
It was promoted out of the historical completion module so the maintained
pipeline no longer depends on legacy completion/reconstruction packages for
ordinary trajectory joins.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point

from awnphen.phenotyping.physical.trajectory import (
    CONTINUATION_TANGENT_SPAN_MM,
    angle_deg,
    chunk_vectors,
    distal_tangent,
    path_length,
)


COVERAGE_DISTANCE_MM = 0.5


def _cumulative_lengths(path):
    out = [0.0]
    for left, right in zip(path, path[1:]):
        out.append(
            out[-1]
            + math.hypot(
                right[0] - left[0],
                right[1] - left[1],
            )
        )
    return out


def _coverage_tail_candidate(
    current_can,
    raw_path,
    canonical_path_mm,
    source_id=None,
):
    """Resolve support by path-to-path coverage, not a single nearest-tip cut."""
    if len(current_can) < 2 or len(canonical_path_mm) < 2:
        return None
    current_line = LineString(current_can)
    current_length = float(current_line.length)
    incoming = distal_tangent(current_can)
    if incoming is None:
        return None

    best = None
    for reverse in (False, True):
        raw = list(reversed(raw_path)) if reverse else list(raw_path)
        can = (
            list(reversed(canonical_path_mm))
            if reverse
            else list(canonical_path_mm)
        )
        distances = [
            float(Point(point).distance(current_line))
            for point in can
        ]
        covered = [
            index
            for index, distance in enumerate(distances)
            if distance <= COVERAGE_DISTANCE_MM
        ]
        if not covered:
            continue

        frontier = max(covered)
        if frontier >= len(can) - 1:
            continue
        suffix_can = can[frontier:]
        if len(suffix_can) < 2:
            continue

        projection = float(current_line.project(Point(can[frontier])))
        current_distal_gap = max(0.0, current_length - projection)
        join_gap = math.hypot(
            can[frontier][0] - current_can[-1][0],
            can[frontier][1] - current_can[-1][1],
        )
        extension = current_can[-1][1] - min(
            point[1] for point in suffix_can
        )
        if extension <= 0.0:
            continue

        suffix_vectors, _ = chunk_vectors(suffix_can, 2.0)
        if not suffix_vectors:
            continue
        angle = angle_deg(incoming, suffix_vectors[0])
        local_turns = [
            angle_deg(left, right)
            for left, right in zip(
                suffix_vectors,
                suffix_vectors[1:],
            )
        ]
        local_turns = [
            value for value in local_turns if value is not None
        ]
        max_internal_turn = max(local_turns, default=0.0)

        cumulative = _cumulative_lengths(can)
        covered_arc = cumulative[frontier]
        residual_arc = cumulative[-1] - cumulative[frontier]
        covered_fraction = (
            covered_arc / cumulative[-1]
            if cumulative[-1] > 0
            else 0.0
        )

        candidate = {
            "raw_path": raw,
            "canonical_path_mm": can,
            "source_evidence_id": source_id,
            "resolution_source": (
                "source" if source_id is not None else "fused"
            ),
            "resolved_entry_index": frontier,
            "resolved_distance_mm": float(join_gap),
            "resolved_angle_deg": (
                None if angle is None else float(angle)
            ),
            "resolved_extension_mm": float(extension),
            "resolved_distal_y_mm": float(
                min(point[1] for point in suffix_can)
            ),
            "resolved_suffix_length_mm": float(
                path_length(suffix_can)
            ),
            "resolved_max_internal_turn_deg": float(
                max_internal_turn
            ),
            "coverage_frontier_index": int(frontier),
            "coverage_distance_mm": COVERAGE_DISTANCE_MM,
            "covered_arc_mm": float(covered_arc),
            "covered_fraction": float(covered_fraction),
            "residual_tail_arc_mm": float(residual_arc),
            "current_distal_gap_mm": float(current_distal_gap),
            "coverage_join_gap_mm": float(join_gap),
        }
        rank = (
            float(current_distal_gap),
            999.0 if angle is None else float(angle),
            float(max_internal_turn),
            -float(residual_arc),
            "" if source_id is None else str(source_id),
        )
        if best is None or rank < best[0]:
            best = (rank, candidate)
    return None if best is None else best[1]


def _resolved_path_candidate(
    current_can,
    raw_path,
    canonical_path_mm,
    source_id=None,
):
    tip = current_can[-1]
    incoming = distal_tangent(current_can)
    if incoming is None:
        return None
    best = None
    for reverse in (False, True):
        raw = list(reversed(raw_path)) if reverse else list(raw_path)
        can = (
            list(reversed(canonical_path_mm))
            if reverse
            else list(canonical_path_mm)
        )
        entry = min(
            range(len(can)),
            key=lambda index: math.hypot(
                can[index][0] - tip[0],
                can[index][1] - tip[1],
            ),
        )
        suffix_can = can[entry:]
        if len(suffix_can) < 2:
            continue
        distance = math.hypot(
            suffix_can[0][0] - tip[0],
            suffix_can[0][1] - tip[1],
        )

        # Match the historical local continuation vector exactly: start at the
        # support point nearest the current tip and follow 1.5 mm toward the
        # distal side in this candidate orientation.
        tangent_distance = 0.0
        distal = entry
        while (
            distal < len(can) - 1
            and tangent_distance < CONTINUATION_TANGENT_SPAN_MM
        ):
            tangent_distance += math.hypot(
                can[distal + 1][0] - can[distal][0],
                can[distal + 1][1] - can[distal][1],
            )
            distal += 1
        tangent = (
            None
            if distal == entry
            else (
                can[distal][0] - can[entry][0],
                can[distal][1] - can[entry][1],
            )
        )
        angle = None if tangent is None else angle_deg(
            incoming,
            tangent,
        )
        extension = tip[1] - min(
            point[1] for point in suffix_can
        )
        suffix_length = path_length(suffix_can)

        vectors, _ = chunk_vectors(suffix_can, 2.0)
        internal_turns = [
            angle_deg(left, right)
            for left, right in zip(vectors, vectors[1:])
        ]
        internal_turns = [
            value for value in internal_turns
            if value is not None
        ]
        max_internal_turn = max(internal_turns, default=0.0)

        rank_key = (
            999.0 if angle is None else float(angle),
            float(max_internal_turn),
            float(distance),
            -float(suffix_length),
            "" if source_id is None else str(source_id),
        )
        candidate = {
            "raw_path": raw,
            "canonical_path_mm": can,
            "source_evidence_id": source_id,
            "resolved_entry_index": entry,
            "resolved_distance_mm": float(distance),
            "resolved_angle_deg": (
                None if angle is None else float(angle)
            ),
            "resolved_extension_mm": float(extension),
            "resolved_distal_y_mm": float(
                min(point[1] for point in suffix_can)
            ),
            "resolved_suffix_length_mm": float(suffix_length),
            "resolved_max_internal_turn_deg": float(
                max_internal_turn
            ),
        }
        if best is None or rank_key < best[0]:
            best = (rank_key, candidate)
    return None if best is None else best[1]


def resolve_support_path(
    current_can,
    support,
    *,
    source_aware: bool = False,
    coverage_aware: bool = False,
):
    """Resolve the best usable suffix of one support against a current path."""
    options = []
    if source_aware:
        for source in support.get("source_paths", []):
            resolved = _resolved_path_candidate(
                current_can,
                source["raw_path"],
                source["canonical_path_mm"],
                source.get("evidence_id"),
            )
            if resolved is None and coverage_aware:
                resolved = _coverage_tail_candidate(
                    current_can,
                    source["raw_path"],
                    source["canonical_path_mm"],
                    source.get("evidence_id"),
                )
            if resolved is not None:
                options.append(resolved)

    fused = _resolved_path_candidate(
        current_can,
        support["raw_path"],
        support["canonical_path_mm"],
        None,
    )
    if fused is None and coverage_aware:
        fused = _coverage_tail_candidate(
            current_can,
            support["raw_path"],
            support["canonical_path_mm"],
            None,
        )
    if fused is not None:
        fused["resolution_source"] = "fused"
    if not options:
        return fused

    if fused is not None:
        max_distal_loss = CONTINUATION_TANGENT_SPAN_MM
        options = [
            item
            for item in options
            if (
                item["resolved_distal_y_mm"]
                - fused["resolved_distal_y_mm"]
                <= max_distal_loss
            )
        ]
    if not options:
        return fused

    candidates = options + ([] if fused is None else [fused])
    candidates.sort(
        key=lambda item: (
            (
                999.0
                if item["resolved_angle_deg"] is None
                else item["resolved_angle_deg"]
            ),
            item["resolved_max_internal_turn_deg"],
            item["resolved_distance_mm"],
            -item["resolved_suffix_length_mm"],
            item["source_evidence_id"] or "",
        )
    )
    chosen = candidates[0]
    chosen["resolution_source"] = (
        "fused" if chosen is fused else "source"
    )
    return chosen


def append_support(current_raw, current_can, support):
    """Append the resolved suffix of one support to a current path."""
    tip = current_can[-1]
    support_raw = support["raw_path"]
    support_can = support["canonical_path_mm"]
    index = support.get("resolved_entry_index")
    if index is None:
        index = min(
            range(len(support_can)),
            key=lambda i: math.hypot(
                support_can[i][0] - tip[0],
                support_can[i][1] - tip[1],
            ),
        )
    index = int(index)
    suffix_raw = support_raw[index:]
    suffix_can = support_can[index:]
    if len(suffix_can) < 2:
        return None

    current_vectors, _ = chunk_vectors(current_can, 2.0)
    suffix_vectors, _ = chunk_vectors(suffix_can, 2.0)
    join_reference = (
        current_vectors[-1] if current_vectors else None
    )
    angles = (
        [
            angle_deg(join_reference, value)
            for value in suffix_vectors
        ]
        if join_reference
        else []
    )
    angles = [value for value in angles if value is not None]
    max_turn = max(angles, default=0.0)
    return (
        list(current_raw) + list(suffix_raw),
        list(current_can) + list(suffix_can),
        index,
        float(max_turn),
    )


__all__ = [
    "COVERAGE_DISTANCE_MM",
    "resolve_support_path",
    "append_support",
]
