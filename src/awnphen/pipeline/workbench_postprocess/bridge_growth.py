"""Frozen Awn Studio hop ranking with an explicit bridge-direction gate.

The production ranker compares the current trajectory direction with the
candidate support direction, but a nearby parallel support can still require a
nearly perpendicular connector from the current tip to the support entry point.
This wrapper repeatedly asks the production ranker for its best candidate and
rejects only candidates whose connector is both non-trivial in length and too
far from the current distal direction.
"""
from __future__ import annotations

import json
import math
import sys

from shapely.geometry import Point

from awnphen.phenotyping.physical.growth.config import DEFAULT_UNIFIED_GROWTH_CONFIG
from awnphen.phenotyping.physical.growth.geometry import (
    _join_turn_metrics,
    _recent_trajectory,
)
from awnphen.phenotyping.physical.growth.growth import (
    _wide_rank_next_support as _production_rank_next_support,
)
from awnphen.phenotyping.physical.support_integration import resolve_support_path
from awnphen.phenotyping.physical.trajectory import (
    angle_deg,
    continuation_tangent,
    distal_tangent,
    multiscale_continuation_angle,
    path_length,
)


BRIDGE_MIN_GAP_MM = DEFAULT_UNIFIED_GROWTH_CONFIG.growth_min_extension_mm
BRIDGE_MAX_ANGLE_DEG = 60.0

# Temporary experiment diagnostics for the IMG_9811 Spikelet 45 failure.
# Retained diagnostic for the historical IMG_9811 failure case.
DIAGNOSTIC_TARGET_SUPPORT_IDS = {
    "hyp_awn_image_9753f6febf9a7c67f9b8",
}
_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG


def _diagnose_candidate(current_can, support, *, spikelet_id, reserved_owner, used_ids):
    sid = str(support["support_hypothesis_id"])
    if sid not in DIAGNOSTIC_TARGET_SUPPORT_IDS:
        return

    payload = {
        "event": "growth_candidate_diagnostic",
        "spikelet_id": str(spikelet_id),
        "support_hypothesis_id": sid,
        "current_length_mm": float(path_length(current_can)),
        "current_tip_mm": [float(v) for v in current_can[-1]],
    }
    owner = reserved_owner.get(sid)
    payload["reserved_owner"] = owner
    if sid in used_ids:
        payload["decision"] = "reject"
        payload["reason"] = "used"
        print("[postprocess-lab] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
        return
    if owner is not None and owner != spikelet_id:
        payload["decision"] = "reject"
        payload["reason"] = "reserved_owner"
        print("[postprocess-lab] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
        return

    tip_point = Point(current_can[-1])
    canonical_line = support.get("canonical_line")
    if canonical_line is not None:
        payload["tip_to_line_mm"] = float(tip_point.distance(canonical_line))
        if payload["tip_to_line_mm"] > _CONFIG.growth_max_distance_mm:
            payload["decision"] = "reject"
            payload["reason"] = "prefilter_distance"
            print("[postprocess-lab] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
            return

    resolved = resolve_support_path(
        current_can,
        support,
        source_aware=False,
        coverage_aware=True,
    )
    if resolved is None:
        payload["decision"] = "reject"
        payload["reason"] = "resolve_none"
        print("[postprocess-lab] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
        return

    extension = float(resolved["resolved_extension_mm"])
    distance = float(resolved["resolved_distance_mm"])
    local_angle = resolved["resolved_angle_deg"]
    internal_turn = float(resolved["resolved_max_internal_turn_deg"])
    payload.update({
        "extension_mm": extension,
        "distance_mm": distance,
        "local_angle_deg": None if local_angle is None else float(local_angle),
        "internal_turn_deg": internal_turn,
        "entry_index": int(resolved["resolved_entry_index"]),
    })

    recent = _recent_trajectory(current_can)
    support_tangent, _ = continuation_tangent(
        resolved["canonical_path_mm"],
        current_can[-1],
    )
    trend_angle = (
        None if recent is None or support_tangent is None else angle_deg(recent, support_tangent)
    )
    multiscale_angle, _ = multiscale_continuation_angle(
        current_can,
        resolved["canonical_path_mm"],
        current_can[-1],
    )
    payload["trend_angle_deg"] = None if trend_angle is None else float(trend_angle)
    payload["multiscale_angle_deg"] = None if multiscale_angle is None else float(multiscale_angle)

    suffix_can = list(resolved["canonical_path_mm"])[int(resolved["resolved_entry_index"]):]
    join_turn = None if len(suffix_can) < 2 else _join_turn_metrics(current_can, suffix_can)
    if join_turn is not None:
        payload.update(join_turn)

    bridge_distance, bridge_angle = _bridge_metrics(current_can, {**support, **resolved})
    payload["bridge_distance_mm"] = float(bridge_distance)
    payload["bridge_angle_deg"] = None if bridge_angle is None else float(bridge_angle)

    checks = [
        (extension < _CONFIG.growth_min_extension_mm, "extension"),
        (distance > _CONFIG.growth_max_distance_mm, "distance"),
        (local_angle is None or local_angle > _CONFIG.growth_max_local_angle_deg, "local_angle"),
        (internal_turn > _CONFIG.growth_max_internal_turn_deg, "internal_turn"),
        (trend_angle is not None and trend_angle > _CONFIG.growth_max_trend_angle_deg, "trend_angle"),
        (multiscale_angle is not None and multiscale_angle > _CONFIG.growth_max_multiscale_angle_deg, "multiscale_angle"),
        (
            join_turn is not None
            and join_turn["join_local_turn_deg"] > _CONFIG.join_max_local_turn_deg
            and join_turn["join_excess_turn_deg"] > _CONFIG.join_max_excess_turn_deg,
            "join_turn",
        ),
        (
            bridge_distance > BRIDGE_MIN_GAP_MM
            and bridge_angle is not None
            and bridge_angle > BRIDGE_MAX_ANGLE_DEG,
            "bridge_angle",
        ),
    ]
    rejected = [reason for failed, reason in checks if failed]
    payload["decision"] = "reject" if rejected else "pass"
    payload["reason"] = rejected[0] if rejected else "passes_all_gates"
    payload["all_failed_checks"] = rejected
    print("[postprocess-lab] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


def _bridge_metrics(current_can, candidate):
    """Return connector distance/angle for current tip -> candidate entry."""
    tip = current_can[-1]
    path = candidate["canonical_path_mm"]
    entry_index = int(candidate["resolved_entry_index"])
    entry = path[entry_index]
    bridge = (entry[0] - tip[0], entry[1] - tip[1])
    distance = float(math.hypot(*bridge))

    incoming = distal_tangent(current_can)
    bridge_angle = None
    if incoming is not None and distance > 1e-9:
        bridge_angle = angle_deg(incoming, bridge)

    return distance, bridge_angle


def rank_next_support(
    current_can,
    pool,
    used_ids,
    *,
    spikelet_id,
    reserved_owner,
    branch_prediction_keys=(),
    crossing_guard=None,
):
    """Return the best production-ranked support that also passes bridge geometry."""
    excluded = set(used_ids)

    for support in pool:
        _diagnose_candidate(
            current_can,
            support,
            spikelet_id=spikelet_id,
            reserved_owner=reserved_owner,
            used_ids=excluded,
        )

    while True:
        production_kwargs = {
            "spikelet_id": spikelet_id,
            "reserved_owner": reserved_owner,
        }
        if branch_prediction_keys:
            production_kwargs["branch_prediction_keys"] = branch_prediction_keys
        if crossing_guard is not None:
            production_kwargs["crossing_guard"] = crossing_guard
        candidate = _production_rank_next_support(
            current_can,
            pool,
            excluded,
            **production_kwargs,
        )
        if candidate is None:
            return None

        distance, bridge_angle = _bridge_metrics(current_can, candidate)
        annotated = {
            **candidate,
            "bridge_distance_mm": float(distance),
            "bridge_angle_deg": None if bridge_angle is None else float(bridge_angle),
            "bridge_gate_max_deg": float(BRIDGE_MAX_ANGLE_DEG),
        }

        # When the entry point is closer than the minimum meaningful growth extension,
        # the connector direction is numerically unstable and biologically
        # uninformative. Reuse the canonical growth scale instead of inventing
        # a separate bridge-gap threshold.
        if distance <= BRIDGE_MIN_GAP_MM or bridge_angle is None:
            return annotated

        if bridge_angle <= BRIDGE_MAX_ANGLE_DEG:
            return annotated

        # Reject this lateral track switch and ask the production ranker for the
        # next-best candidate under the frozen Workbench bridge policy.
        excluded.add(str(candidate["support_hypothesis_id"]))


__all__ = [
    "BRIDGE_MAX_ANGLE_DEG",
    "BRIDGE_MIN_GAP_MM",
    "rank_next_support",
]
