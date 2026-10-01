"""Candidate ranking and single-branch growth for Unified Growth v1."""
from __future__ import annotations

from awnphen.phenotyping.physical.support_integration import (
    append_support,
    resolve_support_path,
)
from awnphen.phenotyping.physical.trajectory import (
    angle_deg,
    continuation_tangent,
    multiscale_continuation_angle,
    path_length,
)
from shapely.geometry import Point

from .config import DEFAULT_UNIFIED_GROWTH_CONFIG
from .geometry import _join_turn_metrics, _recent_trajectory

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG
GROWTH_MAX_HOPS = _CONFIG.growth_max_hops
GROWTH_MIN_EXTENSION_MM = _CONFIG.growth_min_extension_mm
GROWTH_MAX_DISTANCE_MM = _CONFIG.growth_max_distance_mm
GROWTH_MAX_LOCAL_ANGLE_DEG = _CONFIG.growth_max_local_angle_deg
GROWTH_MAX_TREND_ANGLE_DEG = _CONFIG.growth_max_trend_angle_deg
GROWTH_MAX_INTERNAL_TURN_DEG = _CONFIG.growth_max_internal_turn_deg
GROWTH_MAX_MULTISCALE_ANGLE_DEG = _CONFIG.growth_max_multiscale_angle_deg
JOIN_MAX_LOCAL_TURN_DEG = _CONFIG.join_max_local_turn_deg
JOIN_MAX_EXCESS_TURN_DEG = _CONFIG.join_max_excess_turn_deg


CROSS_PREDICTION_LOW_CONFIDENCE = 0.35
CROSS_PREDICTION_LARGE_GAP_MM = 1.0
CROSS_PREDICTION_SHARP_LOCAL_TURN_DEG = 18.0
CROSS_PREDICTION_SHARP_EXCESS_TURN_DEG = 6.0
CROSS_PREDICTION_MIN_RISK_FLAGS = 2


def _cross_prediction_risk_flags(confidence, distance_mm, join_turn):
    flags = []
    if float(confidence) < CROSS_PREDICTION_LOW_CONFIDENCE:
        flags.append("low_confidence")
    if float(distance_mm) >= CROSS_PREDICTION_LARGE_GAP_MM:
        flags.append("large_gap")
    if (
        float(join_turn["join_local_turn_deg"]) >= CROSS_PREDICTION_SHARP_LOCAL_TURN_DEG
        or float(join_turn["join_excess_turn_deg"]) >= CROSS_PREDICTION_SHARP_EXCESS_TURN_DEG
    ):
        flags.append("suspicious_join")
    return tuple(flags)


def _is_cross_prediction(branch_prediction_keys, support):
    current = set(branch_prediction_keys or ())
    candidate = set(support.get("prediction_keys") or ())
    return bool(current and candidate and current.isdisjoint(candidate))


def _wide_rank_next_support(
    current_can,
    pool,
    used_ids,
    *,
    spikelet_id,
    reserved_owner,
    branch_prediction_keys=(),
):
    tip = current_can[-1]
    recent = _recent_trajectory(current_can)
    best = None
    tip_point = Point(tip)

    for support in pool:
        sid = support["support_hypothesis_id"]
        if sid in used_ids:
            continue
        owner = reserved_owner.get(sid)
        if owner is not None and owner != spikelet_id:
            continue
        canonical_line = support.get("canonical_line")
        if canonical_line is not None and tip_point.distance(canonical_line) > GROWTH_MAX_DISTANCE_MM:
            continue

        resolved = resolve_support_path(
            current_can,
            support,
            source_aware=False,
            coverage_aware=True,
        )
        if resolved is None:
            continue

        extension = float(resolved["resolved_extension_mm"])
        distance = float(resolved["resolved_distance_mm"])
        local_angle = resolved["resolved_angle_deg"]
        internal_turn = float(resolved["resolved_max_internal_turn_deg"])

        if extension < GROWTH_MIN_EXTENSION_MM:
            continue
        if distance > GROWTH_MAX_DISTANCE_MM:
            continue
        if local_angle is None or local_angle > GROWTH_MAX_LOCAL_ANGLE_DEG:
            continue
        if internal_turn > GROWTH_MAX_INTERNAL_TURN_DEG:
            continue

        support_tangent, _ = continuation_tangent(
            resolved["canonical_path_mm"],
            tip,
        )
        trend_angle = (
            None
            if recent is None or support_tangent is None
            else angle_deg(recent, support_tangent)
        )
        if trend_angle is not None and trend_angle > GROWTH_MAX_TREND_ANGLE_DEG:
            continue

        multiscale_angle, multiscale_diagnostics = multiscale_continuation_angle(
            current_can,
            resolved["canonical_path_mm"],
            tip,
        )
        if (
            multiscale_angle is not None
            and multiscale_angle > GROWTH_MAX_MULTISCALE_ANGLE_DEG
        ):
            continue

        entry_index = int(resolved["resolved_entry_index"])
        suffix_can = list(resolved["canonical_path_mm"])[entry_index:]
        if len(suffix_can) < 2:
            continue
        join_turn = _join_turn_metrics(current_can, suffix_can)
        if (
            join_turn["join_local_turn_deg"] > JOIN_MAX_LOCAL_TURN_DEG
            and join_turn["join_excess_turn_deg"] > JOIN_MAX_EXCESS_TURN_DEG
        ):
            continue

        support_confidence = float(support.get("confidence", 0.0))
        cross_prediction = _is_cross_prediction(branch_prediction_keys, support)
        cross_prediction_risk_flags = _cross_prediction_risk_flags(
            support_confidence,
            distance,
            join_turn,
        )
        if (
            cross_prediction
            and len(cross_prediction_risk_flags) >= CROSS_PREDICTION_MIN_RISK_FLAGS
        ):
            continue

        trend_for_score = float(local_angle if trend_angle is None else trend_angle)
        multiscale_for_score = float(
            trend_for_score if multiscale_angle is None else multiscale_angle
        )
        score = (
            1.00 * float(local_angle)
            + 0.45 * trend_for_score
            + 0.35 * multiscale_for_score
            + 7.5 * distance
            + 0.18 * internal_turn
            - 2.2 * min(extension, 8.0)
            - 2.0 * support_confidence
        )

        candidate = {
            **support,
            **resolved,
            "raw_path": resolved["raw_path"],
            "canonical_path_mm": resolved["canonical_path_mm"],
            "skeleton_distance_mm": distance,
            "extension_mm": extension,
            "cross_prediction": bool(cross_prediction),
            "cross_prediction_risk_flags": list(cross_prediction_risk_flags),
            "angle_deg": float(local_angle),
            "trend_angle_deg": trend_angle,
            "multiscale_angle_deg": multiscale_angle,
            "multiscale_diagnostics": multiscale_diagnostics,
            **join_turn,
            "growth_score": float(score),
        }
        key = (
            score,
            distance,
            float(local_angle),
            -extension,
            sid,
        )
        if best is None or key < best[0]:
            best = (key, candidate)

    return None if best is None else best[1]


def grow_branch(seed, pool, globally_claimed, reserved_owner):
    spikelet_id = str(seed["spikelet_id"])
    seed_id = str(seed["support_hypothesis_id"])
    current_raw = list(seed["raw_path"])
    current_can = list(seed["canonical_path_mm"])
    used = set(globally_claimed)
    used.add(seed_id)
    local_ids = [seed_id]
    branch_prediction_keys = set(seed.get("prediction_keys") or ())
    steps = []

    for hop in range(GROWTH_MAX_HOPS):
        support = _wide_rank_next_support(
            current_can,
            pool,
            used,
            spikelet_id=spikelet_id,
            reserved_owner=reserved_owner,
            branch_prediction_keys=branch_prediction_keys,
        )
        if support is None:
            break
        appended = append_support(current_raw, current_can, support)
        if appended is None:
            break
        next_raw, next_can, entry_index, max_turn = appended
        sid = str(support["support_hypothesis_id"])
        used.add(sid)
        local_ids.append(sid)
        branch_prediction_keys.update(support.get("prediction_keys") or ())
        current_raw = next_raw
        current_can = next_can
        steps.append(
            {
                "hop": hop + 1,
                "support_hypothesis_id": sid,
                "distance_mm": float(support["skeleton_distance_mm"]),
                "join_angle_deg": float(support["angle_deg"]),
                "trend_angle_deg": support.get("trend_angle_deg"),
                "multiscale_angle_deg": support.get("multiscale_angle_deg"),
                "join_local_turn_deg": support.get("join_local_turn_deg"),
                "join_intrinsic_turn_deg": support.get("join_intrinsic_turn_deg"),
                "join_excess_turn_deg": support.get("join_excess_turn_deg"),
                "extension_mm": float(support["extension_mm"]),
                "cross_prediction": bool(support.get("cross_prediction", False)),
                "cross_prediction_risk_flags": list(support.get("cross_prediction_risk_flags") or []),
                "growth_score": float(support["growth_score"]),
                "bridge_distance_mm": support.get("bridge_distance_mm"),
                "bridge_angle_deg": support.get("bridge_angle_deg"),
                "bridge_gate_max_deg": support.get("bridge_gate_max_deg"),
                "entry_index": int(entry_index),
                "max_join_turn_deg": float(max_turn),
            }
        )

    final_length = float(path_length(current_can))
    angle_cost = sum(float(row["join_angle_deg"]) for row in steps)
    distance_cost = sum(float(row["distance_mm"]) for row in steps)
    branch_score = (
        final_length
        + 0.75 * len(steps)
        - 0.025 * angle_cost
        - 0.25 * distance_cost
        - 0.35 * float(seed["seed_score"])
    )
    return {
        "spikelet_id": spikelet_id,
        "seed_hypothesis_id": seed_id,
        "seed_mode": seed["mode"],
        "seed_score": float(seed["seed_score"]),
        "seed_length_mm": float(seed["length_mm"]),
        "raw_path": current_raw,
        "canonical_path_mm": current_can,
        "final_length_mm": final_length,
        "growth_hops": len(steps),
        "support_hypothesis_ids": local_ids,
        "absorbed_hypothesis_ids": local_ids[1:],
        "steps": steps,
        "branch_score": float(branch_score),
    }

__all__ = [
    "_cross_prediction_risk_flags",
    "_is_cross_prediction",
    "_wide_rank_next_support",
    "grow_branch",
]
