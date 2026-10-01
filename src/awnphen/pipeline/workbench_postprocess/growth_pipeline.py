"""Frozen page-level post-processing entry for Awn Studio.

This policy reuses the maintained Unified Growth implementation while injecting
the bridge-direction ranker and strict seed-grouping behavior validated in the
former 8782 twin.
"""
from __future__ import annotations

from awnphen.phenotyping.physical.growth.pipeline import (
    run_unified_growth_page as _production_run_page,
)

from .bridge_growth import (
    BRIDGE_MAX_ANGLE_DEG,
    BRIDGE_MIN_GAP_MM,
    rank_next_support,
)
from .seed_discovery import (
    EXPERIMENT_ID as SEED_EXPERIMENT_ID,
    discover_provisional_seeds,
)


EXPERIMENT_ID = (
    f"postprocess-lab-bridge-gate-"
    f"{BRIDGE_MAX_ANGLE_DEG:g}deg-{BRIDGE_MIN_GAP_MM:g}mm + "
    f"{SEED_EXPERIMENT_ID}"
)


def run_page(
    evidence_result,
    page: str,
    *,
    calibration,
    forced_spikelet_attachments=(),
    inspection_sink=None,
):
    """Run Unified Growth with the frozen bridge-direction gate."""
    return _production_run_page(
        evidence_result,
        page,
        calibration=calibration,
        forced_spikelet_attachments=forced_spikelet_attachments,
        inspection_sink=inspection_sink,
        rank_next_support=rank_next_support,
        seed_discovery_runner=discover_provisional_seeds,
    )


__all__ = ["EXPERIMENT_ID", "run_page"]
