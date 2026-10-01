from awnphen.pipeline.workbench_postprocess import bridge_growth


def test_bridge_gate_skips_lateral_parallel_track(monkeypatch):
    current = [(0.0, 3.0), (0.0, 1.5), (0.0, 0.0)]

    lateral = {
        "support_hypothesis_id": "parallel-track",
        "canonical_path_mm": [(1.0, 0.0), (1.0, -2.0), (1.0, -4.0)],
        "resolved_entry_index": 0,
    }
    forward = {
        "support_hypothesis_id": "forward-track",
        "canonical_path_mm": [(0.2, -0.4), (0.2, -2.0), (0.2, -4.0)],
        "resolved_entry_index": 0,
    }

    def fake_ranker(current_can, pool, used_ids, *, spikelet_id, reserved_owner):
        if lateral["support_hypothesis_id"] not in used_ids:
            return lateral
        if forward["support_hypothesis_id"] not in used_ids:
            return forward
        return None

    monkeypatch.setattr(
        bridge_growth,
        "_production_rank_next_support",
        fake_ranker,
    )

    chosen = bridge_growth.rank_next_support(
        current,
        [lateral, forward],
        set(),
        spikelet_id="spikelet",
        reserved_owner={},
    )

    assert chosen["support_hypothesis_id"] == "forward-track"
    assert chosen["bridge_angle_deg"] < bridge_growth.BRIDGE_MAX_ANGLE_DEG
    assert chosen["bridge_distance_mm"] > bridge_growth.BRIDGE_MIN_GAP_MM


def test_bridge_gate_ignores_nearly_contiguous_connector(monkeypatch):
    current = [(0.0, 3.0), (0.0, 1.5), (0.0, 0.0)]
    candidate = {
        "support_hypothesis_id": "near-tip",
        "canonical_path_mm": [(0.05, 0.0), (0.05, -2.0)],
        "resolved_entry_index": 0,
    }

    monkeypatch.setattr(
        bridge_growth,
        "_production_rank_next_support",
        lambda *args, **kwargs: candidate,
    )

    chosen = bridge_growth.rank_next_support(
        current,
        [candidate],
        set(),
        spikelet_id="spikelet",
        reserved_owner={},
    )

    assert chosen["support_hypothesis_id"] == "near-tip"
    assert chosen["bridge_distance_mm"] <= bridge_growth.BRIDGE_MIN_GAP_MM
