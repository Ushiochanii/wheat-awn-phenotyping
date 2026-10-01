"""JSON-safe observability projection for Unified Growth.

This module exposes information that already exists during Unified Growth so
application and review layers can explain a result without rerunning the
scientific pipeline. It must not participate in candidate ranking, ownership,
branch selection, or measurement.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shapely.geometry import mapping


SCHEMA_VERSION = "unified_growth_inspection_v1"


def _points(values) -> list[list[float]]:
    return [[float(point[0]), float(point[1])] for point in values or ()]


def _optional_float(value):
    return None if value is None else float(value)


def _support_view(support: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "support_hypothesis_id": str(support["support_hypothesis_id"]),
        "raw_path": _points(support.get("raw_path")),
        "confidence": float(support.get("confidence", 0.0)),
        "length_mm": float(support.get("length_mm", 0.0)),
    }


def _seed_view(seed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_support_view(seed),
        "mode": str(seed["mode"]),
        "seed_score": float(seed["seed_score"]),
        "root_distance_mm": float(seed["root_distance_mm"]),
        "projection_distance_mm": float(seed["projection_distance_mm"]),
        "axis_deviation_deg": _optional_float(seed.get("axis_deviation_deg")),
    }


def _step_view(
    step: Mapping[str, Any],
    supports_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    support_id = str(step["support_hypothesis_id"])
    support = supports_by_id.get(support_id)
    return {
        "hop": int(step["hop"]),
        "support_hypothesis_id": support_id,
        "raw_path": (_points(step["resolved_raw_path"]) if step.get("resolved_raw_path") is not None
                     else [] if support is None else _points(support.get("raw_path"))),
        "support_confidence": None if support is None else float(support.get("confidence", 0.0)),
        "support_length_mm": None if support is None else float(support.get("length_mm", 0.0)),
        "distance_mm": float(step["distance_mm"]),
        "join_angle_deg": float(step["join_angle_deg"]),
        "trend_angle_deg": _optional_float(step.get("trend_angle_deg")),
        "multiscale_angle_deg": _optional_float(step.get("multiscale_angle_deg")),
        "join_local_turn_deg": _optional_float(step.get("join_local_turn_deg")),
        "join_intrinsic_turn_deg": _optional_float(step.get("join_intrinsic_turn_deg")),
        "join_excess_turn_deg": _optional_float(step.get("join_excess_turn_deg")),
        "extension_mm": float(step["extension_mm"]),
        "cross_prediction": bool(step.get("cross_prediction", False)),
        "cross_prediction_risk_flags": list(step.get("cross_prediction_risk_flags") or []),
        "growth_score": float(step["growth_score"]),
        "entry_index": int(step["entry_index"]),
        "max_join_turn_deg": float(step["max_join_turn_deg"]),
        "ownership_mode": step.get("ownership_mode"),
        "ownership_competitor_count": (
            None
            if step.get("ownership_competitor_count") is None
            else int(step["ownership_competitor_count"])
        ),
        "ownership_gap_rel": _optional_float(step.get("ownership_gap_rel")),
        **({"junction_clip": dict(step["junction_clip"]),
            "growth_stop_reason": str(step["growth_stop_reason"])}
           if step.get("junction_clip") else {}),
        **{key: step[key] for key in (
            "crossing_splice", "foreign_body_clip", "growth_stop_reason"
        ) if key in step},
    }


def _branch_trace_view(
    branch: Mapping[str, Any],
    supports_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an internal, JSON-safe Seed -> Hop trace for one grown branch."""

    seed_id = str(branch["seed_hypothesis_id"])
    seed = supports_by_id.get(seed_id)
    return {
        "spikelet_id": str(branch["spikelet_id"]),
        "seed": {
            "support_hypothesis_id": seed_id,
            "raw_path": [] if seed is None else _points(seed.get("raw_path")),
        },
        "hops": [
            _step_view(step, supports_by_id)
            for step in branch.get("steps", ())
        ],
        "final_raw_path": _points(branch.get("raw_path")),
        "final_length_mm": float(branch.get("final_length_mm", 0.0)),
        "branch_score": float(branch.get("branch_score", 0.0)),
    }


def _candidate_branch_traces(
    growth_row: Mapping[str, Any],
    support_pool: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return internal traces for every sibling branch retained by growth."""

    supports_by_id = {
        str(item["support_hypothesis_id"]): item
        for item in support_pool
    }
    return [
        _branch_trace_view(branch, supports_by_id)
        for branch in growth_row.get("_branches", ())
    ]


def build_unified_growth_inspection(
    *,
    spikelets: Sequence[Mapping[str, Any]],
    support_pool: Sequence[Mapping[str, Any]],
    seed_groups: Mapping[str, Sequence[Mapping[str, Any]]],
    growth: Sequence[Mapping[str, Any]],
    representatives: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project in-memory Unified Growth state into a compact JSON-safe contract."""

    supports_by_id = {
        str(item["support_hypothesis_id"]): item
        for item in support_pool
    }
    spikelets_by_id = {
        str(item["id"]): item
        for item in spikelets
    }
    growth_by_spikelet = {
        str(item["spikelet_id"]): item
        for item in growth
    }
    representative_by_spikelet = {
        str(item["spikelet_id"]): item
        for item in representatives
    }

    record_ids = sorted(
        set(spikelets_by_id)
        | set(seed_groups)
        | set(growth_by_spikelet)
        | set(representative_by_spikelet)
    )
    records: dict[str, dict[str, Any]] = {}

    for spikelet_id in record_ids:
        growth_row = growth_by_spikelet.get(spikelet_id)
        winner = None if growth_row is None else growth_row.get("winner")
        representative = representative_by_spikelet.get(spikelet_id)
        spikelet = spikelets_by_id.get(spikelet_id)

        seed_candidates = [
            _seed_view(seed)
            for seed in seed_groups.get(spikelet_id, ())
        ]
        seed_by_id = {
            row["support_hypothesis_id"]: row
            for row in seed_candidates
        }
        winner_seed_id = None if winner is None else str(winner["seed_hypothesis_id"])
        winner_seed = None if winner_seed_id is None else seed_by_id.get(winner_seed_id)

        steps = []
        if winner is not None:
            steps = [
                _step_view(step, supports_by_id)
                for step in winner.get("steps", ())
            ]

        related_ids = {
            row["support_hypothesis_id"]
            for row in seed_candidates
        }
        if winner is not None:
            related_ids.update(str(value) for value in winner.get("support_hypothesis_ids", ()))
            related_ids.update(
                str(event["support_hypothesis_id"])
                for event in winner.get("ownership_events", ())
                if event.get("support_hypothesis_id") is not None
            )

        related_supports = [
            _support_view(supports_by_id[support_id])
            for support_id in sorted(related_ids)
            if support_id in supports_by_id
        ]

        records[spikelet_id] = {
            "spikelet_id": spikelet_id,
            "spikelet_geometry": (
                None
                if spikelet is None
                else mapping(spikelet["geometry"])
            ),
            "seed_candidates": seed_candidates,
            "winner_seed": winner_seed,
            "related_supports": related_supports,
            "steps": steps,
            "winner": (
                None
                if winner is None
                else {
                    "seed_hypothesis_id": winner_seed_id,
                    "seed_mode": winner.get("seed_mode"),
                    "seed_score": float(winner.get("seed_score", 0.0)),
                    "seed_length_mm": float(winner.get("seed_length_mm", 0.0)),
                    "final_raw_path": _points(winner.get("raw_path")),
                    "final_length_mm": float(winner.get("final_length_mm", 0.0)),
                    "growth_hops": int(winner.get("growth_hops", 0)),
                    "absorbed_hypothesis_ids": [
                        str(value)
                        for value in winner.get("absorbed_hypothesis_ids", ())
                    ],
                    "branch_score": float(winner.get("branch_score", 0.0)),
                    "ownership_events": [
                        {
                            "support_hypothesis_id": str(event["support_hypothesis_id"]),
                            "result": str(event["result"]),
                            "score": float(event["score"]),
                            "best_competing_score": float(event["best_competing_score"]),
                            "gap_rel": _optional_float(event.get("gap_rel")),
                        }
                        for event in winner.get("ownership_events", ())
                    ],
                }
            ),
            "alternatives": (
                []
                if growth_row is None
                else [
                    {
                        "seed_hypothesis_id": str(row["seed_hypothesis_id"]),
                        "seed_mode": str(row["seed_mode"]),
                        "final_length_mm": float(row["final_length_mm"]),
                        "growth_hops": int(row["growth_hops"]),
                        "branch_score": float(row["branch_score"]),
                    }
                    for row in growth_row.get("alternatives", ())
                ]
            ),
            # Private observability payload for application/debug rendering.
            # Scientific consumers should ignore this field.
            "_candidate_branches": (
                []
                if growth_row is None
                else _candidate_branch_traces(growth_row, support_pool)
            ),
            "representative": (
                None
                if representative is None
                else {
                    "candidate_id": str(representative["candidate_id"]),
                    "seed_hypothesis_id": str(representative["seed_hypothesis_id"]),
                    "seed_mode": str(representative["seed_mode"]),
                    "raw_path": _points(representative.get("raw_path")),
                    "length_mm_internal": float(representative["length_mm_internal"]),
                    "growth_hops": int(representative["growth_hops"]),
                    **{key: representative[key] for key in (
                        "review_reason", "endpoint_status"
                    ) if key in representative},
                    "canonical_source_spikelet_id": (
                        None
                        if representative.get("canonical_source_spikelet_id") is None
                        else str(representative["canonical_source_spikelet_id"])
                    ),
                }
            ),
        }

    return {
        "schema": SCHEMA_VERSION,
        "support_pool": [
            _support_view(item)
            for item in sorted(
                support_pool,
                key=lambda row: str(row["support_hypothesis_id"]),
            )
        ],
        "records": records,
    }


__all__ = ["SCHEMA_VERSION", "build_unified_growth_inspection"]
