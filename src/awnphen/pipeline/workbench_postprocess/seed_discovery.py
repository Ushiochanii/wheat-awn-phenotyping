"""Frozen bounded, group-diverse seed discovery for Awn Studio."""
from __future__ import annotations

from awnphen.phenotyping.physical.growth.seeds import (
    discover_provisional_seeds as _production_discover,
)

from .seed_grouping import (
    EXPANDED_CANDIDATE_CAP,
    GROUPING_VERSION,
    group_seed_candidates,
    select_group_diverse_seeds,
)

EXPERIMENT_ID = GROUPING_VERSION


def discover_provisional_seeds(pool, spikelets):
    """Expand modestly, validate attachments, then preserve group diversity.

    Candidate expansion is exactly 4x the production per-spikelet cap (16 instead
    of 4). Grouping cannot rescue an invalid candidate: only groups containing a
    trustworthy attachment are allowed to contribute seeds.
    """
    discovered, reserved_owner = _production_discover(
        pool,
        spikelets,
        max_seeds_per_spikelet=EXPANDED_CANDIDATE_CAP,
    )
    spikelets_by_id = {str(item["id"]): item for item in spikelets}

    selected = {}
    for spikelet_id, seeds in discovered.items():
        spikelet = spikelets_by_id.get(str(spikelet_id))
        if spikelet is None:
            continue
        grouped = group_seed_candidates(seeds, spikelet)
        kept = select_group_diverse_seeds(grouped)
        if kept:
            selected[spikelet_id] = kept

    # Keep the production ownership reservation for every support that was
    # unambiguously root-associated with a spikelet. Group filtering decides
    # which supports may START branches. It must not release rejected root-like
    # supports back into the global growth pool, where another spikelet could
    # absorb them later as a continuation.
    return selected, reserved_owner


__all__ = ["EXPERIMENT_ID", "discover_provisional_seeds"]
