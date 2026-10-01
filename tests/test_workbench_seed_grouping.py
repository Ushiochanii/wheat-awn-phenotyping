from __future__ import annotations

from shapely.geometry import box

from awnphen.pipeline.workbench_postprocess.seed_grouping import (
    FINAL_SEED_CAP,
    GROUPING_VERSION,
    group_seed_candidates,
    select_group_diverse_seeds,
)


def _seed(
    seed_id,
    path,
    *,
    score,
    confidence=0.9,
    mode="direct",
    root_distance=0.0,
    projection_distance=0.0,
):
    return {
        "support_hypothesis_id": seed_id,
        "canonical_path_mm": path,
        "raw_path": path,
        "seed_score": score,
        "confidence": confidence,
        "length_mm": sum(
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip(path, path[1:])
        ),
        "mode": mode,
        "root_distance_mm": root_distance,
        "projection_distance_mm": projection_distance,
        "axis_deviation_deg": 0.0,
        "spikelet_id": "s1",
    }


def test_frozen_grouping_version_is_v24_strict_final():
    assert GROUPING_VERSION == "seed-grouping-v2.4-cap16-strict-final"


def test_duplicate_strong_direct_seeds_share_one_group_and_anchor():
    spikelet = {
        "id": "s1",
        "canonical_geometry": box(-1.0, 0.0, 1.0, 4.0),
    }
    seeds = [
        _seed("a", [(0.0, 0.0), (0.0, -2.0), (0.0, -6.0)], score=-3.0),
        _seed("b", [(0.1, 0.0), (0.1, -2.0), (0.1, -8.0)], score=-2.5),
    ]

    grouped = group_seed_candidates(seeds, spikelet)

    assert len(grouped) == 2
    assert grouped[0]["awn_group_id"] == grouped[1]["awn_group_id"]
    assert grouped[0]["awn_group_size"] == 2
    assert grouped[0]["awn_group_anchor_seed_id"] == "a"
    assert grouped[0]["awn_group_anchor_type"] == "direct"
    assert all(seed["awn_group_selectable"] for seed in grouped)

    selected = select_group_diverse_seeds(grouped)
    assert [seed["support_hypothesis_id"] for seed in selected] == ["a", "b"]


def test_distinct_parallel_roots_remain_separate_groups():
    spikelet = {
        "id": "s1",
        "canonical_geometry": box(-4.0, 0.0, 4.0, 4.0),
    }
    seeds = [
        _seed("left", [(-2.0, 0.0), (-2.0, -3.0), (-2.0, -7.0)], score=-3.0),
        _seed("right", [(2.0, 0.0), (2.0, -3.0), (2.0, -7.0)], score=-2.9),
    ]

    grouped = group_seed_candidates(seeds, spikelet)

    assert len(grouped) == 2
    assert grouped[0]["awn_group_id"] != grouped[1]["awn_group_id"]
    assert all(seed["awn_group_size"] == 1 for seed in grouped)


def test_lone_projected_seed_cannot_create_a_group():
    spikelet = {
        "id": "s1",
        "canonical_geometry": box(-1.0, 0.0, 1.0, 4.0),
    }
    projected = _seed(
        "projected",
        [(0.0, -0.3), (0.0, -3.0), (0.0, -7.0)],
        score=-2.0,
        mode="projected",
        projection_distance=0.2,
    )

    assert group_seed_candidates([projected], spikelet) == []


def test_two_consistent_projected_seeds_form_consensus_group():
    spikelet = {
        "id": "s1",
        "canonical_geometry": box(-1.0, 0.0, 1.0, 4.0),
    }
    seeds = [
        _seed(
            "p1",
            [(0.0, -0.2), (0.0, -3.0), (0.0, -7.0)],
            score=-2.0,
            mode="projected",
            projection_distance=0.2,
        ),
        _seed(
            "p2",
            [(0.1, -0.2), (0.1, -3.0), (0.1, -8.0)],
            score=-1.8,
            mode="projected",
            projection_distance=0.2,
        ),
    ]

    grouped = group_seed_candidates(seeds, spikelet)

    assert len(grouped) == 2
    assert grouped[0]["awn_group_id"] == grouped[1]["awn_group_id"]
    assert grouped[0]["awn_group_anchor_type"] == "projected_consensus"
    assert all(seed["awn_group_selectable"] for seed in grouped)


def test_group_diversity_gets_first_claim_on_final_slots():
    annotated = []
    for index in range(FINAL_SEED_CAP + 2):
        group_id = f"g{index}"
        annotated.append(
            {
                "support_hypothesis_id": f"s{index}",
                "awn_group_id": group_id,
                "awn_group_rank": 1,
                "awn_group_selectable": True,
                "length_mm": 10.0 + index,
                "confidence": 0.9,
                "seed_score": float(index),
            }
        )

    selected = select_group_diverse_seeds(annotated)

    assert len(selected) == FINAL_SEED_CAP
    assert len({seed["awn_group_id"] for seed in selected}) == FINAL_SEED_CAP
