"""Frozen bounded, reliable seed grouping for Awn Studio.

Grouping has one narrow purpose: duplicate observations of one physical awn
must not consume every provisional-seed slot. Grouping never makes a weak
candidate valid by itself.

A group is eligible when either:
1. it contains a trustworthy direct spikelet attachment; or
2. it contains at least two mutually consistent projected candidates, providing
   consensus for a root that is missing from the mask.

The candidate pool is deliberately bounded at 4x the production seed cap.
"""
from __future__ import annotations

import math
from collections import defaultdict

import shapely
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from awnphen.phenotyping.physical.growth.config import DEFAULT_UNIFIED_GROWTH_CONFIG
from awnphen.phenotyping.physical.trajectory import angle_deg

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG

PRODUCTION_SEED_CAP = _CONFIG.max_provisional_seeds_per_spikelet
EXPANDED_CANDIDATE_CAP = PRODUCTION_SEED_CAP * 4
FINAL_SEED_CAP = PRODUCTION_SEED_CAP

MIN_SEED_LENGTH_MM = _CONFIG.growth_min_extension_mm
MAX_AXIS_DEVIATION_DEG = _CONFIG.orientation_vote_max_axis_angle_deg
DIRECT_ROOT_MAX_MM = _CONFIG.direct_root_max_mm
STRONG_ROOT_MAX_MM = _CONFIG.project_root_max_distance_mm
STRONG_CONFIDENCE = _CONFIG.primary_confidence

# These five grouping thresholds are retained from the earlier grouping
# experiment, but now they only decide duplicate-like geometry after candidate
# validity has been checked. They no longer grant a group survival by themselves.
GROUP_ANCHOR_MAX_MM = 1.50
GROUP_INITIAL_ANGLE_MAX_DEG = 25.0
GROUP_PATH_NEAR_MM = 0.60
GROUP_MIN_SHORT_COVERAGE = 0.12
GROUP_TIP_TO_LINE_MAX_MM = 0.90

PROJECTED_CONSENSUS_MIN_MEMBERS = 2

GROUPING_VERSION = "seed-grouping-v2.4-cap16-strict-final"


def _rank_key(seed):
    return (
        float(seed["seed_score"]),
        -float(seed["length_mm"]),
        -float(seed["confidence"]),
        str(seed["support_hypothesis_id"]),
    )


def _basic_candidate(seed) -> bool:
    """Cheap per-candidate validity before any grouping."""
    if float(seed.get("length_mm", 0.0)) < MIN_SEED_LENGTH_MM:
        return False
    if float(seed.get("axis_deviation_deg", float("inf"))) > MAX_AXIS_DEVIATION_DEG:
        return False

    mode = seed.get("mode")
    if mode == "direct":
        return float(seed.get("root_distance_mm", float("inf"))) <= DIRECT_ROOT_MAX_MM
    if mode == "projected":
        return (
            float(seed.get("projection_distance_mm", float("inf")))
            <= STRONG_ROOT_MAX_MM
        )
    return False


def _strong_direct_anchor(seed) -> bool:
    """A direct seed can establish a group only if attachment evidence is strong."""
    if seed.get("mode") != "direct" or not _basic_candidate(seed):
        return False
    root_distance = float(seed.get("root_distance_mm", float("inf")))
    confidence = float(seed.get("confidence", 0.0))
    return (
        root_distance <= STRONG_ROOT_MAX_MM
        or (
            root_distance <= DIRECT_ROOT_MAX_MM
            and confidence >= STRONG_CONFIDENCE
        )
    )


def _initial_direction(path, span_mm: float = 2.0):
    if len(path) < 2:
        return None
    start = path[0]
    distance = 0.0
    for index in range(1, len(path)):
        left = path[index - 1]
        right = path[index]
        distance += math.hypot(right[0] - left[0], right[1] - left[1])
        if distance >= span_mm or index == len(path) - 1:
            vector = (right[0] - start[0], right[1] - start[1])
            if math.hypot(*vector) <= 1e-9:
                return None
            return vector
    return None


def _candidate_features(seed, spikelet):
    path = list(seed["canonical_path_mm"])
    if len(path) < 2:
        return None
    root = Point(path[0])
    anchor, _ = nearest_points(spikelet["canonical_geometry"], root)
    return {
        "path": path,
        "line": LineString(path),
        "sample_points": shapely.points(path),
        "anchor": (float(anchor.x), float(anchor.y)),
        "direction": _initial_direction(path),
        "tip": Point(path[-1]),
    }


def _coverage_fraction(sample_points, other_line) -> float:
    if len(sample_points) == 0:
        return 0.0
    near = int(shapely.dwithin(sample_points, other_line, GROUP_PATH_NEAR_MM).sum())
    return float(near) / float(len(sample_points))


def _same_physical_awn(left, right, left_features, right_features) -> bool:
    """Conservative duplicate-like test. This never validates a group by itself."""
    if left_features is None or right_features is None:
        return False

    la = left_features["anchor"]
    ra = right_features["anchor"]
    if math.hypot(la[0] - ra[0], la[1] - ra[1]) > GROUP_ANCHOR_MAX_MM:
        return False

    ld = left_features["direction"]
    rd = right_features["direction"]
    if ld is None or rd is None:
        return False
    if angle_deg(ld, rd) > GROUP_INITIAL_ANGLE_MAX_DEG:
        return False

    if float(left["length_mm"]) <= float(right["length_mm"]):
        shorter_points = left_features["sample_points"]
        other_line = right_features["line"]
    else:
        shorter_points = right_features["sample_points"]
        other_line = left_features["line"]

    coverage = _coverage_fraction(shorter_points, other_line)
    tip_distance = min(
        float(left_features["tip"].distance(right_features["line"])),
        float(right_features["tip"].distance(left_features["line"])),
    )
    return (
        coverage >= GROUP_MIN_SHORT_COVERAGE
        and tip_distance <= GROUP_TIP_TO_LINE_MAX_MM
    )


def _group_anchor(component):
    """Return (anchor seed, anchor type), or None when the group is unreliable."""
    direct_anchors = [seed for seed in component if _strong_direct_anchor(seed)]
    if direct_anchors:
        return min(direct_anchors, key=_rank_key), "direct"

    projected = [seed for seed in component if seed.get("mode") == "projected"]
    if len(projected) >= PROJECTED_CONSENSUS_MIN_MEMBERS:
        return min(projected, key=_rank_key), "projected_consensus"

    return None


def _selectable_final_seed(seed, anchor_type: str) -> bool:
    """Final seeds are stricter than mere group members.

    A direct-group backup must itself satisfy the strong-direct rule. A projected
    seed is selectable only inside a projected-consensus group that already has
    multiple mutually consistent projected members.
    """
    if anchor_type == "direct":
        return _strong_direct_anchor(seed)
    if anchor_type == "projected_consensus":
        return seed.get("mode") == "projected" and _basic_candidate(seed)
    return False


def group_seed_candidates(seeds, spikelet):
    """Filter, group duplicate-like candidates, then validate each group."""
    rows = [dict(seed) for seed in seeds if _basic_candidate(seed)]
    if not rows:
        return []

    features = [_candidate_features(seed, spikelet) for seed in rows]
    parent = list(range(len(rows)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index in range(len(rows)):
        for right_index in range(left_index + 1, len(rows)):
            if _same_physical_awn(
                rows[left_index],
                rows[right_index],
                features[left_index],
                features[right_index],
            ):
                union(left_index, right_index)

    components = defaultdict(list)
    for index, row in enumerate(rows):
        components[find(index)].append(row)

    viable = []
    for component in components.values():
        anchor_info = _group_anchor(component)
        if anchor_info is None:
            continue
        anchor, anchor_type = anchor_info
        viable.append((anchor, anchor_type, component))

    viable.sort(key=lambda item: _rank_key(item[0]))

    annotated = []
    for group_index, (anchor, anchor_type, component) in enumerate(viable, start=1):
        ranked = sorted(
            component,
            key=lambda seed: (
                0 if seed is anchor else 1,
                *_rank_key(seed),
            ),
        )
        group_id = f"{spikelet['id']}:awn_group_{group_index:02d}"
        member_ids = [str(seed["support_hypothesis_id"]) for seed in ranked]
        anchor_id = str(anchor["support_hypothesis_id"])
        for rank, seed in enumerate(ranked, start=1):
            annotated.append(
                {
                    **seed,
                    "awn_group_id": group_id,
                    "awn_group_rank": rank,
                    "awn_group_size": len(ranked),
                    "awn_group_anchor_seed_id": anchor_id,
                    "awn_group_anchor_type": anchor_type,
                    "awn_group_selectable": _selectable_final_seed(seed, anchor_type),
                    "awn_group_member_ids": member_ids,
                }
            )
    return annotated


def select_group_diverse_seeds(annotated):
    """Give distinct valid groups first claim on slots, then fill reliable backups."""
    by_group = defaultdict(list)
    for seed in annotated:
        by_group[seed["awn_group_id"]].append(seed)

    ordered_groups = sorted(
        by_group.values(),
        key=lambda group: _rank_key(group[0]),
    )

    selected = []
    selected_groups = []
    for group in ordered_groups:
        if len(selected) >= FINAL_SEED_CAP:
            break
        anchor = group[0]
        if not anchor.get("awn_group_selectable", False):
            continue
        selected.append(anchor)
        selected_groups.append(group)

    if len(selected) < FINAL_SEED_CAP:
        backups = []
        for group in selected_groups:
            backups.extend(
                seed
                for seed in group[1:]
                if seed.get("awn_group_selectable", False)
            )
        backups.sort(key=_rank_key)
        selected.extend(backups[: FINAL_SEED_CAP - len(selected)])

    return selected


__all__ = [
    "EXPANDED_CANDIDATE_CAP",
    "FINAL_SEED_CAP",
    "GROUPING_VERSION",
    "PROJECTED_CONSENSUS_MIN_MEMBERS",
    "group_seed_candidates",
    "select_group_diverse_seeds",
]
