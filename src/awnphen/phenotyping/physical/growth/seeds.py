"""Provisional root-seed discovery for Unified Growth v1."""
from __future__ import annotations

from collections import defaultdict

from shapely.geometry import Point
from shapely.ops import nearest_points

from awnphen.phenotyping.physical.orientation import seed_axis_deviation_deg

from .config import DEFAULT_UNIFIED_GROWTH_CONFIG
from .geometry import _projected_root_match

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG
DIRECT_ROOT_MAX_MM = _CONFIG.direct_root_max_mm
ROOT_MATCH_PREFILTER_MM = max(
    DIRECT_ROOT_MAX_MM,
    _CONFIG.project_root_ray_mm + _CONFIG.project_root_max_distance_mm,
)
MAX_PROVISIONAL_SEEDS_PER_SPIKELET = _CONFIG.max_provisional_seeds_per_spikelet
SEED_MAX_AXIS_DEVIATION_DEG = _CONFIG.seed_max_axis_deviation_deg


def discover_provisional_seeds(pool, spikelets, *, max_seeds_per_spikelet=None):
    """Return several plausible root-origin segments per spikelet."""
    max_seeds = (
        MAX_PROVISIONAL_SEEDS_PER_SPIKELET
        if max_seeds_per_spikelet is None
        else int(max_seeds_per_spikelet)
    )
    grouped = defaultdict(list)
    support_owner_candidates = defaultdict(list)

    for support in pool:
        can = support["canonical_path_mm"]
        if len(can) < 2:
            continue
        root = can[0]
        root_point = Point(root)
        parent_options = []

        for spikelet in spikelets:
            geometry = spikelet["canonical_geometry"]
            direct_distance = float(root_point.distance(geometry))
            if direct_distance > ROOT_MATCH_PREFILTER_MM:
                continue
            axis_deviation = seed_axis_deviation_deg(can, geometry)
            if (
                axis_deviation is None
                or axis_deviation > SEED_MAX_AXIS_DEVIATION_DEG
            ):
                continue
            closest, _ = nearest_points(geometry, root_point)
            upper_half = float(closest.y) <= float(spikelet["centroid_y"])

            if upper_half and direct_distance <= DIRECT_ROOT_MAX_MM:
                parent_options.append(
                    {
                        "spikelet_id": str(spikelet["id"]),
                        "mode": "direct",
                        "root_distance_mm": direct_distance,
                        "projection_distance_mm": 0.0,
                        "axis_deviation_deg": float(axis_deviation),
                    }
                )
                continue

            projected_distance = _projected_root_match(can, spikelet)
            if projected_distance is not None:
                parent_options.append(
                    {
                        "spikelet_id": str(spikelet["id"]),
                        "mode": "projected",
                        "root_distance_mm": direct_distance,
                        "projection_distance_mm": projected_distance,
                        "axis_deviation_deg": float(axis_deviation),
                    }
                )

        if not parent_options:
            continue

        parent_options.sort(
            key=lambda row: (
                0 if row["mode"] == "direct" else 1,
                row["root_distance_mm"] if row["mode"] == "direct" else row["projection_distance_mm"],
                row["spikelet_id"],
            )
        )
        chosen = parent_options[0]
        seed = {
            **support,
            **chosen,
            "seed_score": (
                (0.0 if chosen["mode"] == "direct" else 4.0)
                + min(4.0, chosen["root_distance_mm"])
                + 1.5 * chosen["projection_distance_mm"]
                - 1.5 * support["confidence"]
                - 0.10 * min(30.0, support["length_mm"])
            ),
        }
        grouped[chosen["spikelet_id"]].append(seed)
        support_owner_candidates[support["support_hypothesis_id"]].append(
            chosen["spikelet_id"]
        )

    selected = {}
    for spikelet_id, seeds in grouped.items():
        seeds.sort(
            key=lambda row: (
                row["seed_score"],
                -row["length_mm"],
                -row["confidence"],
                row["support_hypothesis_id"],
            )
        )
        selected[spikelet_id] = seeds[:max_seeds]

    reserved_owner = {}
    for support_id, owners in support_owner_candidates.items():
        uniq = sorted(set(owners))
        if len(uniq) == 1:
            reserved_owner[support_id] = uniq[0]

    return selected, reserved_owner

__all__ = ["discover_provisional_seeds"]
