from __future__ import annotations

from types import SimpleNamespace

import pytest
from shapely.affinity import rotate
from shapely.geometry import box

from awnphen.phenotyping.physical.orientation import (
    ScaleContext,
    estimate_spikelet_anchored_orientation,
)
from awnphen.phenotyping.physical.growth.geometry import (
    _join_turn_metrics,
)
from awnphen.phenotyping.physical.growth.growth import (
    _cross_prediction_risk_flags,
    _is_cross_prediction,
)
from awnphen.phenotyping.physical.growth.seeds import (
    discover_provisional_seeds,
)
from awnphen.phenotyping.physical.growth.supports import (
    _orient_root_to_tip,
)
import awnphen.phenotyping.physical.growth.ownership as ownership_module
from awnphen.phenotyping.physical.growth.ownership import (
    _ownership_allows_share,
    _ownership_gap_rel,
    grow_representatives,
)
from awnphen.phenotyping.physical.growth.config import (
    DEFAULT_UNIFIED_GROWTH_CONFIG,
)


def test_ownership_gap_uses_relative_margin() -> None:
    # The validation case that motivated competitive ownership:
    # the worse sibling is ~7.9% away, so it must not share the fragment.
    assert _ownership_gap_rel(7.996, 8.684) == pytest.approx(
        abs(7.996 - 8.684) / 8.684
    )
    assert not _ownership_allows_share(7.996, 8.684)

    # Truly ambiguous competition remains shareable.
    assert _ownership_allows_share(8.0, 8.3)


def test_grow_representatives_retains_full_internal_loser_branch(monkeypatch) -> None:
    winner_branch = {
        "spikelet_id": "s1",
        "seed_hypothesis_id": "seed-a",
        "seed_mode": "direct",
        "seed_score": 1.0,
        "seed_length_mm": 5.0,
        "raw_path": [(0.0, 0.0), (0.0, 5.0), (0.0, 9.0)],
        "canonical_path_mm": [(0.0, 0.0), (0.0, 5.0), (0.0, 9.0)],
        "final_length_mm": 9.0,
        "growth_hops": 1,
        "support_hypothesis_ids": ["seed-a", "hop-a1"],
        "absorbed_hypothesis_ids": ["hop-a1"],
        "steps": [{"hop": 1, "support_hypothesis_id": "hop-a1"}],
        "branch_score": 9.5,
        "ownership_events": [],
    }
    loser_branch = {
        "spikelet_id": "s1",
        "seed_hypothesis_id": "seed-b",
        "seed_mode": "direct",
        "seed_score": 1.2,
        "seed_length_mm": 4.0,
        "raw_path": [(2.0, 0.0), (2.0, 4.0), (3.0, 7.0)],
        "canonical_path_mm": [(2.0, 0.0), (2.0, 4.0), (3.0, 7.0)],
        "final_length_mm": 7.2,
        "growth_hops": 1,
        "support_hypothesis_ids": ["seed-b", "hop-b1"],
        "absorbed_hypothesis_ids": ["hop-b1"],
        "steps": [{"hop": 1, "support_hypothesis_id": "hop-b1"}],
        "branch_score": 7.1,
        "ownership_events": [],
    }

    monkeypatch.setattr(
        ownership_module,
        "grow_competing_branches",
        lambda *args, **kwargs: [loser_branch, winner_branch],
    )

    representatives, diagnostics = grow_representatives(
        {
            "s1": [
                {
                    "support_hypothesis_id": "seed-a",
                    "seed_score": 1.0,
                    "length_mm": 5.0,
                }
            ]
        },
        pool=[],
        reserved_owner={},
    )

    assert representatives[0]["seed_hypothesis_id"] == "seed-a"
    assert diagnostics[0]["alternatives"] == [
        {
            "seed_hypothesis_id": "seed-b",
            "seed_mode": "direct",
            "final_length_mm": 7.2,
            "growth_hops": 1,
            "branch_score": 7.1,
        }
    ]
    assert diagnostics[0]["_branches"][0]["seed_hypothesis_id"] == "seed-a"
    assert diagnostics[0]["_branches"][1]["seed_hypothesis_id"] == "seed-b"
    assert diagnostics[0]["_branches"][1]["raw_path"] == loser_branch["raw_path"]
    assert diagnostics[0]["_branches"][1]["steps"] == loser_branch["steps"]


def test_join_turn_distinguishes_smooth_from_new_kink() -> None:
    current = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]

    smooth_suffix = [(3.0, 0.0), (4.0, 0.0), (5.0, 0.0), (6.0, 0.0)]
    smooth = _join_turn_metrics(current, smooth_suffix)
    assert smooth["join_local_turn_deg"] == pytest.approx(0.0)
    assert smooth["join_excess_turn_deg"] == pytest.approx(0.0)

    right_angle_suffix = [(3.0, 0.0), (3.0, 1.0), (3.0, 2.0), (3.0, 3.0)]
    kink = _join_turn_metrics(current, right_angle_suffix)
    assert kink["join_local_turn_deg"] > 45.0
    assert kink["join_excess_turn_deg"] > 45.0


def test_cross_prediction_identity_uses_prediction_provenance() -> None:
    same_prediction = {"prediction_keys": ("provider:tile_0006:4",)}
    different_prediction = {"prediction_keys": ("provider:tile_0005:11",)}
    branch_keys = {"provider:tile_0006:4"}

    assert not _is_cross_prediction(branch_keys, same_prediction)
    assert _is_cross_prediction(branch_keys, different_prediction)


def test_cross_prediction_risk_flags_match_review_thresholds() -> None:
    flags = _cross_prediction_risk_flags(
        0.301,
        0.198,
        {"join_local_turn_deg": 26.565, "join_excess_turn_deg": 0.0},
    )
    assert flags == ("low_confidence", "suspicious_join")

    same_prediction_large_gap_flags = _cross_prediction_risk_flags(
        0.620,
        1.463,
        {"join_local_turn_deg": 17.65, "join_excess_turn_deg": 4.656},
    )
    assert same_prediction_large_gap_flags == ("large_gap",)


def test_promoted_default_policy_is_explicit() -> None:
    cfg = DEFAULT_UNIFIED_GROWTH_CONFIG
    assert cfg.primary_confidence == pytest.approx(0.50)
    assert cfg.compaction_overlap == pytest.approx(0.92)
    assert cfg.max_provisional_seeds_per_spikelet == 4
    assert cfg.orientation_vote_max_axis_angle_deg == pytest.approx(45.0)
    assert cfg.orientation_vote_max_distance_mm == pytest.approx(5.0)
    assert cfg.seed_max_axis_deviation_deg == pytest.approx(75.0)
    assert cfg.join_max_local_turn_deg == pytest.approx(22.0)
    assert cfg.join_max_excess_turn_deg == pytest.approx(8.0)
    assert cfg.ownership_share_rel_margin == pytest.approx(0.05)


def test_page_orientation_ignores_transverse_awn_clutter() -> None:
    base = [
        ("spikelet", "s1", box(-1.0, 10.0, 1.0, 20.0)),
        ("spikelet", "s2", box(9.0, 10.0, 11.0, 20.0)),
        ("awn", "a1", box(-0.3, 0.0, 0.3, 9.0)),
        ("awn", "a2", box(9.7, 0.0, 10.3, 9.0)),
        # Horizontal guide-line fragments touching the spikelet tops.
        ("awn", "clutter1", box(-4.0, 8.5, 4.0, 9.2)),
        ("awn", "clutter2", box(6.0, 8.5, 14.0, 9.2)),
        ("awn", "clutter3", box(-5.0, 9.0, 15.0, 9.6)),
    ]
    hypotheses = []
    evidence_by_id = {}
    for class_name, evidence_id, geometry in base:
        hypotheses.append(
            SimpleNamespace(
                hypothesis_id=evidence_id,
                class_name=class_name,
                status=SimpleNamespace(value="accepted"),
                evidence_ids=(evidence_id,),
                geometry=rotate(geometry, 90.0, origin=(0.0, 0.0)),
            )
        )
        evidence_by_id[evidence_id] = SimpleNamespace(confidence=0.9)

    cfg = DEFAULT_UNIFIED_GROWTH_CONFIG
    transform, diagnostics = estimate_spikelet_anchored_orientation(
        hypotheses,
        evidence_by_id,
        ScaleContext(5.0, 5.0, True),
        primary_confidence=0.5,
        vote_max_axis_angle_deg=cfg.orientation_vote_max_axis_angle_deg,
        vote_max_distance_mm=cfg.orientation_vote_max_distance_mm,
    )

    centers = [
        (
            hypothesis.class_name,
            hypothesis.hypothesis_id,
            transform.raw_px_to_canonical_mm(
                (hypothesis.geometry.centroid.x, hypothesis.geometry.centroid.y)
            ),
        )
        for hypothesis in hypotheses
    ]
    true_awn_y = [
        point[1]
        for class_name, hypothesis_id, point in centers
        if class_name == "awn" and hypothesis_id in {"a1", "a2"}
    ]
    spikelet_y = [
        point[1]
        for class_name, _, point in centers
        if class_name == "spikelet"
    ]

    assert diagnostics["policy"] == "spikelet_axis_anchored"
    assert diagnostics["spikelet_axis_vote_count"] == 2
    assert max(true_awn_y) < min(spikelet_y)


def test_single_spikelet_orientation_defaults_polarity_and_continues() -> None:
    base = [
        ("spikelet", "s1", box(-1.0, 10.0, 1.0, 20.0)),
        # This awn would otherwise provide a polarity vote. With only one
        # spikelet we deliberately skip page-polarity confirmation.
        ("awn", "a1", box(-0.3, 0.0, 0.3, 9.0)),
    ]
    hypotheses = []
    evidence_by_id = {}
    for class_name, evidence_id, geometry in base:
        hypotheses.append(
            SimpleNamespace(
                hypothesis_id=evidence_id,
                class_name=class_name,
                status=SimpleNamespace(value="accepted"),
                evidence_ids=(evidence_id,),
                geometry=rotate(geometry, 90.0, origin=(0.0, 0.0)),
            )
        )
        evidence_by_id[evidence_id] = SimpleNamespace(confidence=0.9)

    cfg = DEFAULT_UNIFIED_GROWTH_CONFIG
    transform, diagnostics = estimate_spikelet_anchored_orientation(
        hypotheses,
        evidence_by_id,
        ScaleContext(5.0, 5.0, True),
        primary_confidence=0.5,
        vote_max_axis_angle_deg=cfg.orientation_vote_max_axis_angle_deg,
        vote_max_distance_mm=cfg.orientation_vote_max_distance_mm,
    )

    canonical_spikelet = transform.geometry_to_canonical_mm(hypotheses[0].geometry)
    min_x, min_y, max_x, max_y = canonical_spikelet.bounds

    assert diagnostics["policy"] == "single_spikelet_default_polarity"
    assert diagnostics["orientation_degraded"] is True
    assert diagnostics["primary_spikelet_count"] == 1
    assert diagnostics["spikelet_axis_vote_count"] == 0
    assert transform.polarity_flipped is False
    assert transform.polarity_confidence == pytest.approx(0.0)
    assert transform.axis_concentration == pytest.approx(0.0)
    assert (max_y - min_y) > (max_x - min_x)


def test_support_direction_is_canonical_root_to_tip() -> None:
    raw = [(10.0, 10.0), (10.0, 5.0), (10.0, 0.0)]
    canonical = [(0.0, 1.0), (0.0, 3.0), (0.0, 8.0)]

    oriented_raw, oriented_canonical = _orient_root_to_tip(raw, canonical)

    assert oriented_raw == list(reversed(raw))
    assert oriented_canonical == list(reversed(canonical))
    assert oriented_canonical[0][1] > oriented_canonical[-1][1]


def test_transverse_line_touching_spikelet_top_cannot_become_seed() -> None:
    spikelet = {
        "id": "s1",
        "canonical_geometry": box(-1.0, 0.0, 1.0, 4.0),
        "centroid_y": 2.0,
    }
    pool = [
        {
            "support_hypothesis_id": "true-awn",
            "raw_path": [(0.0, 0.0), (0.0, -4.0)],
            "canonical_path_mm": [(0.0, 0.0), (0.0, -4.0)],
            "confidence": 0.9,
            "length_mm": 4.0,
        },
        {
            "support_hypothesis_id": "horizontal-guide",
            "raw_path": [(0.0, 0.0), (4.0, 0.0)],
            "canonical_path_mm": [(0.0, 0.0), (4.0, 0.0)],
            "confidence": 0.99,
            "length_mm": 4.0,
        },
    ]

    seeds, reserved_owner = discover_provisional_seeds(pool, [spikelet])

    assert [row["support_hypothesis_id"] for row in seeds["s1"]] == ["true-awn"]
    assert seeds["s1"][0]["axis_deviation_deg"] == pytest.approx(0.0)
    assert "horizontal-guide" not in reserved_owner
