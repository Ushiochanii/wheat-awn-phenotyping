"""Page-level orchestration for the maintained Unified Growth v1 route."""
from __future__ import annotations

import math
import time

from awnphen.phenotyping.detection.spikelet_premerge import preprocess_spikelet_hypotheses
from awnphen.phenotyping.physical.orientation import (
    build_canonical_spikelets,
    estimate_spikelet_anchored_orientation,
    load_scale,
)
from awnphen.phenotyping.detection.reconciliation import reconcile_detection_evidence

from .config import DEFAULT_UNIFIED_GROWTH_CONFIG
from .evidence import _build_compacted_awn_hypotheses
from .ownership import grow_representatives
from .seeds import discover_provisional_seeds
from .supports import build_support_pool

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG


def run_unified_growth_page(
    evidence_result,
    page: str,
    *,
    calibration,
    forced_spikelet_attachments=(),
    inspection_sink=None,
    rank_next_support=None,
    seed_discovery_runner=None,
):
    """Reconstruct one page with Unified Growth v1."""

    timing = {}
    evidence_by_id = {
        str(item.evidence_id): item
        for item in evidence_result.evidence
    }

    started = time.perf_counter()
    awn_hypotheses, compaction = _build_compacted_awn_hypotheses(
        evidence_result.evidence
    )
    timing["awn_compaction_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    spikelet_evidence = tuple(
        item for item in evidence_result.evidence
        if item.class_name == "spikelet"
    )
    spikelet_reconciliation = reconcile_detection_evidence(spikelet_evidence)
    timing["spikelet_reconciliation_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    combined = tuple(spikelet_reconciliation.hypotheses) + tuple(awn_hypotheses)
    cal = calibration[page]
    premerge = preprocess_spikelet_hypotheses(
        combined,
        x_period_px_5mm=float(cal["x"]),
        y_period_px_5mm=float(cal["y"]),
        forced_attachments=forced_spikelet_attachments,
    )
    combined = premerge.hypotheses
    canonical_source_by_spikelet_id = {}
    for hypothesis in combined:
        if hypothesis.class_name != "spikelet":
            continue
        attachment_provenance = [
            item
            for item in hypothesis.provenance
            if item.operation == "attach_spikelet_fragments"
        ]
        if attachment_provenance:
            canonical_source_by_spikelet_id[str(hypothesis.hypothesis_id)] = str(
                attachment_provenance[-1].input_ids[0]
            )
    scale = load_scale(calibration, page)
    skeleton_cache = {}
    transform, orientation_diagnostics = estimate_spikelet_anchored_orientation(
        combined,
        evidence_by_id,
        scale,
        primary_confidence=_CONFIG.primary_confidence,
        vote_max_axis_angle_deg=_CONFIG.orientation_vote_max_axis_angle_deg,
        vote_max_distance_mm=_CONFIG.orientation_vote_max_distance_mm,
    )
    spikelets = build_canonical_spikelets(
        combined,
        evidence_by_id,
        transform,
        primary_confidence=_CONFIG.primary_confidence,
    )
    reconstruction_summary = {
        "page_id": page,
        "orientation_rotation_deg": math.degrees(transform.rotation_rad),
        "polarity_flipped": transform.polarity_flipped,
        "axis_concentration": transform.axis_concentration,
        "polarity_confidence": transform.polarity_confidence,
        "primary_spikelets": len(spikelets),
        "awn_hypotheses": sum(
            hypothesis.class_name == "awn" for hypothesis in combined
        ),
        "orientation_diagnostics": orientation_diagnostics,
    }
    timing["context_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    active_awn_hypotheses = tuple(
        item for item in combined if item.class_name == "awn"
    )
    pool = build_support_pool(
        active_awn_hypotheses,
        transform,
        evidence_by_id,
        skeleton_cache=skeleton_cache,
    )
    seed_discovery = seed_discovery_runner or discover_provisional_seeds
    seed_groups, reserved_owner = seed_discovery(pool, spikelets)
    timing["seed_discovery_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    representatives, growth = grow_representatives(
        seed_groups,
        pool,
        reserved_owner,
        rank_next_support=rank_next_support,
    )
    spikelet_geometry_by_id = {
        str(item["id"]): item["geometry"].wkt
        for item in spikelets
    }
    representatives = [
        {
            **row,
            "spikelet_geometry_wkt": spikelet_geometry_by_id.get(
                str(row.get("spikelet_id"))
            ),
            "canonical_source_spikelet_id": canonical_source_by_spikelet_id.get(
                str(row.get("spikelet_id"))
            ),
        }
        for row in representatives
    ]
    timing["growth_seconds"] = time.perf_counter() - started
    timing["prototype_total_seconds"] = sum(timing.values())

    if inspection_sink is not None:
        from awnphen.phenotyping.inspection.growth import (
            build_unified_growth_inspection,
        )

        inspection_sink(
            build_unified_growth_inspection(
                spikelets=spikelets,
                support_pool=pool,
                seed_groups=seed_groups,
                growth=growth,
                representatives=representatives,
            )
        )

    seed_count = sum(len(rows) for rows in seed_groups.values())
    projected_seeds = sum(
        seed["mode"] == "projected"
        for rows in seed_groups.values()
        for seed in rows
    )
    direct_seeds = seed_count - projected_seeds

    return {
        "representatives": representatives,
        "growth": growth,
        "timing": timing,
        "raw_awn_count": sum(
            item.class_name == "awn" for item in evidence_result.evidence
        ),
        "compacted_awn_hypothesis_count": len(awn_hypotheses),
        "compaction_cluster_count": compaction.cluster_count,
        "primary_spikelet_count": len(spikelets),
        "spikelets_with_seed": len(seed_groups),
        "provisional_seed_count": seed_count,
        "direct_seed_count": direct_seeds,
        "projected_seed_count": projected_seeds,
        "representative_count": len(representatives),
        "growth_hops": sum(
            item["winner"]["growth_hops"] for item in growth
        ),
        "representatives_with_growth": sum(
            item["winner"]["growth_hops"] > 0 for item in growth
        ),
        "reconstruction_summary": reconstruction_summary,
    }

run_page = run_unified_growth_page

__all__ = ["run_unified_growth_page", "run_page"]
