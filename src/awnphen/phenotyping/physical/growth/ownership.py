"""Sibling-seed competition, fragment ownership, and branch selection."""
from __future__ import annotations

from awnphen.phenotyping.physical.support_integration import append_support
from awnphen.phenotyping.physical.trajectory import path_length

from .config import DEFAULT_UNIFIED_GROWTH_CONFIG
from .growth import _wide_rank_next_support

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG
GROWTH_MAX_HOPS = _CONFIG.growth_max_hops
OWNERSHIP_SHARE_REL_MARGIN = _CONFIG.ownership_share_rel_margin


def _ownership_gap_rel(score_a, score_b):
    denom = max(1.0, abs(float(score_a)), abs(float(score_b)))
    return abs(float(score_a) - float(score_b)) / denom


def _ownership_allows_share(score_a, score_b):
    """Return True when sibling branches are close enough to share evidence."""
    return _ownership_gap_rel(score_a, score_b) <= OWNERSHIP_SHARE_REL_MARGIN


def _init_competing_branch(seed, globally_claimed):
    seed_id = str(seed["support_hypothesis_id"])
    return {
        "spikelet_id": str(seed["spikelet_id"]),
        "seed_hypothesis_id": seed_id,
        "seed_mode": seed["mode"],
        "seed_score": float(seed["seed_score"]),
        "seed_length_mm": float(seed["length_mm"]),
        "current_raw": list(seed["raw_path"]),
        "current_can": list(seed["canonical_path_mm"]),
        "used": set(globally_claimed) | {seed_id},
        "denied": set(),
        "local_ids": [seed_id],
        "prediction_keys": set(seed.get("prediction_keys") or ()),
        "steps": [],
        "ownership_events": [],
    }


def _append_competing_support(state, support, *, ownership_mode, competitor_count, gap_rel):
    appended = append_support(
        state["current_raw"], state["current_can"], support
    )
    if appended is None:
        return False
    next_raw, next_can, entry_index, max_turn = appended
    sid = str(support["support_hypothesis_id"])
    state["used"].add(sid)
    state["local_ids"].append(sid)
    state["prediction_keys"].update(support.get("prediction_keys") or ())
    state["current_raw"] = next_raw
    state["current_can"] = next_can
    state["steps"].append(
        {
            "hop": len(state["steps"]) + 1,
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
            "ownership_mode": ownership_mode,
            "ownership_competitor_count": int(competitor_count),
            "ownership_gap_rel": None if gap_rel is None else float(gap_rel),
        }
    )
    return True


def _finish_competing_branch(state):
    final_length = float(path_length(state["current_can"]))
    angle_cost = sum(float(row["join_angle_deg"]) for row in state["steps"])
    distance_cost = sum(float(row["distance_mm"]) for row in state["steps"])
    branch_score = (
        final_length
        + 0.75 * len(state["steps"])
        - 0.025 * angle_cost
        - 0.25 * distance_cost
        - 0.35 * float(state["seed_score"])
    )
    return {
        "spikelet_id": state["spikelet_id"],
        "seed_hypothesis_id": state["seed_hypothesis_id"],
        "seed_mode": state["seed_mode"],
        "seed_score": float(state["seed_score"]),
        "seed_length_mm": float(state["seed_length_mm"]),
        "raw_path": state["current_raw"],
        "canonical_path_mm": state["current_can"],
        "final_length_mm": final_length,
        "growth_hops": len(state["steps"]),
        "support_hypothesis_ids": state["local_ids"],
        "absorbed_hypothesis_ids": state["local_ids"][1:],
        "steps": state["steps"],
        "branch_score": float(branch_score),
        "ownership_events": state["ownership_events"],
    }


def grow_competing_branches(
    seeds,
    pool,
    globally_claimed,
    reserved_owner,
    *,
    rank_next_support=None,
):
    """Grow sibling provisional seeds synchronously with competitive ownership."""
    ranker = rank_next_support or _wide_rank_next_support
    states = [_init_competing_branch(seed, globally_claimed) for seed in seeds]
    ownership = {}

    max_rounds = GROWTH_MAX_HOPS * max(2, len(states) + 1)
    for _round in range(max_rounds):
        proposals = {}
        for idx, state in enumerate(states):
            if len(state["steps"]) >= GROWTH_MAX_HOPS:
                continue
            support = ranker(
                state["current_can"],
                pool,
                state["used"] | state["denied"],
                spikelet_id=state["spikelet_id"],
                reserved_owner=reserved_owner,
                branch_prediction_keys=state["prediction_keys"],
            )
            if support is None:
                continue
            sid = str(support["support_hypothesis_id"])
            proposals.setdefault(sid, []).append((idx, support))

        if not proposals:
            break

        progressed = False
        for support_id, challengers in proposals.items():
            prior = ownership.get(support_id, [])
            current = [
                {
                    "branch_index": idx,
                    "score": float(support["growth_score"]),
                    "support": support,
                }
                for idx, support in challengers
            ]

            if prior:
                best_prior = min(prior, key=lambda row: row["score"])
                for row in current:
                    gap = _ownership_gap_rel(row["score"], best_prior["score"])
                    state = states[row["branch_index"]]
                    if _ownership_allows_share(row["score"], best_prior["score"]):
                        if _append_competing_support(
                            state,
                            row["support"],
                            ownership_mode="shared_with_prior_owner",
                            competitor_count=len(prior) + len(current),
                            gap_rel=gap,
                        ):
                            ownership[support_id].append(
                                {
                                    "branch_index": row["branch_index"],
                                    "score": row["score"],
                                    "hop": len(state["steps"]),
                                }
                            )
                            state["ownership_events"].append(
                                {
                                    "support_hypothesis_id": support_id,
                                    "result": "shared",
                                    "score": row["score"],
                                    "best_competing_score": best_prior["score"],
                                    "gap_rel": gap,
                                }
                            )
                            progressed = True
                    else:
                        state["denied"].add(support_id)
                        state["ownership_events"].append(
                            {
                                "support_hypothesis_id": support_id,
                                "result": "denied_existing_owner",
                                "score": row["score"],
                                "best_competing_score": best_prior["score"],
                                "gap_rel": gap,
                            }
                        )
                continue

            current.sort(key=lambda row: (row["score"], row["branch_index"]))
            best_score = current[0]["score"]
            accepted = []
            for row in current:
                gap = _ownership_gap_rel(row["score"], best_score)
                if _ownership_allows_share(row["score"], best_score):
                    accepted.append((row, gap))
                else:
                    state = states[row["branch_index"]]
                    state["denied"].add(support_id)
                    state["ownership_events"].append(
                        {
                            "support_hypothesis_id": support_id,
                            "result": "denied_better_sibling",
                            "score": row["score"],
                            "best_competing_score": best_score,
                            "gap_rel": gap,
                        }
                    )

            mode = "shared" if len(accepted) > 1 else "exclusive"
            for row, gap in accepted:
                state = states[row["branch_index"]]
                if _append_competing_support(
                    state,
                    row["support"],
                    ownership_mode=mode,
                    competitor_count=len(current),
                    gap_rel=gap,
                ):
                    ownership.setdefault(support_id, []).append(
                        {
                            "branch_index": row["branch_index"],
                            "score": row["score"],
                            "hop": len(state["steps"]),
                        }
                    )
                    state["ownership_events"].append(
                        {
                            "support_hypothesis_id": support_id,
                            "result": mode,
                            "score": row["score"],
                            "best_competing_score": best_score,
                            "gap_rel": gap,
                        }
                    )
                    progressed = True

        if not progressed:
            if all(
                ranker(
                    state["current_can"],
                    pool,
                    state["used"] | state["denied"],
                    spikelet_id=state["spikelet_id"],
                    reserved_owner=reserved_owner,
                )
                is None
                for state in states
            ):
                break

    return [_finish_competing_branch(state) for state in states]


def grow_representatives(
    seed_groups,
    pool,
    reserved_owner,
    *,
    rank_next_support=None,
):
    """Grow sibling seeds competitively, then commit only the winning branch."""
    globally_claimed = set()
    representatives = []
    diagnostics = []

    parent_order = sorted(
        seed_groups,
        key=lambda sid: (
            seed_groups[sid][0]["seed_score"],
            -seed_groups[sid][0]["length_mm"],
            sid,
        ),
    )

    for spikelet_id in parent_order:
        eligible_seeds = [
            seed
            for seed in seed_groups[spikelet_id]
            if seed["support_hypothesis_id"] not in globally_claimed
        ]
        branches = grow_competing_branches(
            eligible_seeds,
            pool,
            globally_claimed,
            reserved_owner,
            rank_next_support=rank_next_support,
        )
        if not branches:
            continue

        branches.sort(
            key=lambda row: (
                -row["branch_score"],
                -row["final_length_mm"],
                row["seed_score"],
                row["seed_hypothesis_id"],
            )
        )
        winner = branches[0]
        globally_claimed.update(winner["support_hypothesis_ids"])

        candidate_id = (
            f"unified_growth_v1_competitive:{spikelet_id}:{winner['seed_hypothesis_id']}"
        )
        representatives.append(
            {
                "status": "SELECTED",
                "spikelet_id": spikelet_id,
                "candidate_id": candidate_id,
                "source": "unified_growth_v1_competitive",
                "seed_hypothesis_id": winner["seed_hypothesis_id"],
                "seed_mode": winner["seed_mode"],
                "absorbed_hypothesis_ids": winner["absorbed_hypothesis_ids"],
                "raw_path": winner["raw_path"],
                "canonical_path_mm": winner["canonical_path_mm"],
                "length_mm_internal": winner["final_length_mm"],
                "growth_hops": winner["growth_hops"],
            }
        )
        diagnostics.append(
            {
                "candidate_id": candidate_id,
                "spikelet_id": spikelet_id,
                "winner": winner,
                "branch_count": len(branches),
                # Internal observability only. Keep the fully grown sibling
                # branches so inspection/UI code can reconstruct Seed -> Hop N
                # without changing representative selection or rerunning growth.
                # This is intentionally not part of the public product contract.
                "_branches": branches,
                "alternatives": [
                    {
                        "seed_hypothesis_id": row["seed_hypothesis_id"],
                        "seed_mode": row["seed_mode"],
                        "final_length_mm": row["final_length_mm"],
                        "growth_hops": row["growth_hops"],
                        "branch_score": row["branch_score"],
                    }
                    for row in branches[1:]
                ],
            }
        )

    return representatives, diagnostics

__all__ = ["_ownership_gap_rel", "_ownership_allows_share", "grow_competing_branches", "grow_representatives"]
