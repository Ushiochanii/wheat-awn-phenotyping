from __future__ import annotations

import json

from shapely.geometry import Polygon

from awnphen.phenotyping.inspection.growth import (
    SCHEMA_VERSION,
    _candidate_branch_traces,
    build_unified_growth_inspection,
)


def test_unified_growth_inspection_projects_seed_and_hop_paths() -> None:
    spikelets = (
        {
            "id": "spikelet-source-1",
            "geometry": Polygon(((0, 0), (4, 0), (4, 4), (0, 4))),
        },
    )
    support_pool = (
        {
            "support_hypothesis_id": "seed-a",
            "raw_path": [(2, 1), (2, -4)],
            "canonical_path_mm": [(0, 0), (0, 5)],
            "confidence": 0.91,
            "length_mm": 5.0,
        },
        {
            "support_hypothesis_id": "hop-b",
            "raw_path": [(2, -4), (3, -8)],
            "canonical_path_mm": [(0, 5), (1, 9)],
            "confidence": 0.83,
            "length_mm": 4.2,
        },
    )
    seed_groups = {
        "spikelet-source-1": (
            {
                **support_pool[0],
                "spikelet_id": "spikelet-source-1",
                "mode": "direct",
                "root_distance_mm": 0.2,
                "projection_distance_mm": 0.0,
                "seed_score": 1.25,
            },
        )
    }
    winner = {
        "spikelet_id": "spikelet-source-1",
        "seed_hypothesis_id": "seed-a",
        "seed_mode": "direct",
        "seed_score": 1.25,
        "seed_length_mm": 5.0,
        "raw_path": [(2, 1), (2, -4), (3, -8)],
        "canonical_path_mm": [(0, 0), (0, 5), (1, 9)],
        "final_length_mm": 9.1,
        "growth_hops": 1,
        "support_hypothesis_ids": ["seed-a", "hop-b"],
        "absorbed_hypothesis_ids": ["hop-b"],
        "steps": [
            {
                "hop": 1,
                "support_hypothesis_id": "hop-b",
                "distance_mm": 0.1,
                "join_angle_deg": 4.0,
                "trend_angle_deg": 3.0,
                "multiscale_angle_deg": 2.0,
                "join_local_turn_deg": 3.5,
                "join_intrinsic_turn_deg": 1.0,
                "join_excess_turn_deg": 2.5,
                "extension_mm": 4.1,
                "growth_score": 2.2,
                "entry_index": 0,
                "max_join_turn_deg": 3.5,
                "ownership_mode": "exclusive",
                "ownership_competitor_count": 1,
                "ownership_gap_rel": 0.0,
            }
        ],
        "branch_score": 9.5,
        "ownership_events": [
            {
                "support_hypothesis_id": "hop-b",
                "result": "exclusive",
                "score": 2.2,
                "best_competing_score": 2.2,
                "gap_rel": 0.0,
            }
        ],
    }
    growth = (
        {
            "candidate_id": "candidate-1",
            "spikelet_id": "spikelet-source-1",
            "winner": winner,
            "branch_count": 1,
            "_branches": [winner],
            "alternatives": [],
        },
    )
    representatives = (
        {
            "status": "SELECTED",
            "spikelet_id": "spikelet-source-1",
            "candidate_id": "candidate-1",
            "source": "unified_growth_v1_competitive",
            "seed_hypothesis_id": "seed-a",
            "seed_mode": "direct",
            "absorbed_hypothesis_ids": ["hop-b"],
            "raw_path": [(2, 1), (2, -4), (3, -8)],
            "canonical_path_mm": [(0, 0), (0, 5), (1, 9)],
            "length_mm_internal": 9.1,
            "growth_hops": 1,
        },
    )

    payload = build_unified_growth_inspection(
        spikelets=spikelets,
        support_pool=support_pool,
        seed_groups=seed_groups,
        growth=growth,
        representatives=representatives,
    )

    assert payload["schema"] == SCHEMA_VERSION
    assert len(payload["support_pool"]) == 2
    record = payload["records"]["spikelet-source-1"]
    assert record["winner_seed"]["support_hypothesis_id"] == "seed-a"
    assert record["winner_seed"]["raw_path"] == [[2.0, 1.0], [2.0, -4.0]]
    assert record["steps"][0]["support_hypothesis_id"] == "hop-b"
    assert record["steps"][0]["raw_path"] == [[2.0, -4.0], [3.0, -8.0]]
    assert record["steps"][0]["ownership_mode"] == "exclusive"
    assert record["_candidate_branches"][0]["seed"]["support_hypothesis_id"] == "seed-a"
    assert record["_candidate_branches"][0]["hops"][0]["support_hypothesis_id"] == "hop-b"
    assert record["representative"]["candidate_id"] == "candidate-1"

    # The application boundary must never depend on Shapely/Python objects.
    json.dumps(payload)


def test_internal_candidate_branch_trace_reconstructs_winner_and_loser_hops() -> None:
    support_pool = (
        {
            "support_hypothesis_id": "seed-a",
            "raw_path": [(0, 0), (0, 5)],
            "confidence": 0.9,
            "length_mm": 5.0,
        },
        {
            "support_hypothesis_id": "hop-a1",
            "raw_path": [(0, 5), (0, 9)],
            "confidence": 0.8,
            "length_mm": 4.0,
        },
        {
            "support_hypothesis_id": "seed-b",
            "raw_path": [(2, 0), (2, 4)],
            "confidence": 0.85,
            "length_mm": 4.0,
        },
        {
            "support_hypothesis_id": "hop-b1",
            "raw_path": [(2, 4), (3, 7)],
            "confidence": 0.7,
            "length_mm": 3.2,
        },
    )
    common_step = {
        "distance_mm": 0.2,
        "join_angle_deg": 5.0,
        "trend_angle_deg": None,
        "multiscale_angle_deg": None,
        "join_local_turn_deg": None,
        "join_intrinsic_turn_deg": None,
        "join_excess_turn_deg": None,
        "extension_mm": 3.0,
        "growth_score": 1.0,
        "entry_index": 0,
        "max_join_turn_deg": 5.0,
        "ownership_mode": "exclusive",
        "ownership_competitor_count": 1,
        "ownership_gap_rel": 0.0,
    }
    growth_row = {
        "spikelet_id": "s1",
        "_branches": [
            {
                "spikelet_id": "s1",
                "seed_hypothesis_id": "seed-a",
                "raw_path": [(0, 0), (0, 5), (0, 9)],
                "final_length_mm": 9.0,
                "branch_score": 9.5,
                "steps": [
                    {
                        **common_step,
                        "hop": 1,
                        "support_hypothesis_id": "hop-a1",
                    }
                ],
            },
            {
                "spikelet_id": "s1",
                "seed_hypothesis_id": "seed-b",
                "raw_path": [(2, 0), (2, 4), (3, 7)],
                "final_length_mm": 7.2,
                "branch_score": 7.1,
                "steps": [
                    {
                        **common_step,
                        "hop": 1,
                        "support_hypothesis_id": "hop-b1",
                    }
                ],
            },
        ],
    }

    traces = _candidate_branch_traces(growth_row, support_pool)

    assert len(traces) == 2
    assert traces[0]["seed"]["support_hypothesis_id"] == "seed-a"
    assert traces[0]["hops"][0]["support_hypothesis_id"] == "hop-a1"
    assert traces[0]["final_raw_path"] == [[0.0, 0.0], [0.0, 5.0], [0.0, 9.0]]
    assert traces[1]["seed"]["support_hypothesis_id"] == "seed-b"
    assert traces[1]["hops"][0]["support_hypothesis_id"] == "hop-b1"
    assert traces[1]["final_raw_path"] == [[2.0, 0.0], [2.0, 4.0], [3.0, 7.0]]
    json.dumps(traces)
