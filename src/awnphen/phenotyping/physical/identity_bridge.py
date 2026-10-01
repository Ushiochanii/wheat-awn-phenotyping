"""Resolve Unified Growth spikelet identities onto canonical physical spikelets.

Unified Growth may reconstruct a spikelet hypothesis with a new deterministic ID
even when it represents the same physical object as the upstream Phase 4A
spikelet. Downstream semantics must therefore never assume raw hypothesis-ID
stability across reconstruction boundaries.

Resolution priority:
1. explicit provenance alias from spikelet premerge;
2. exact hypothesis ID;
3. conservative geometry crosswalk;
4. unresolved.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from shapely import wkt as shapely_wkt


GEOMETRY_CROSSWALK_MIN_IOU = 0.90
GEOMETRY_CROSSWALK_MIN_MARGIN = 0.10


@dataclass(frozen=True, slots=True)
class SpikeletIdentityResolution:
    spikelet: object | None
    status: str
    source_spikelet_id: str
    canonical_spikelet_id: str | None
    metadata: Mapping[str, object]


def geometry_iou(left, right) -> float:
    if left is None or right is None or left.is_empty or right.is_empty:
        return 0.0
    union = left.union(right).area
    if union <= 0:
        return 0.0
    return float(left.intersection(right).area / union)


def geometry_crosswalk(row, spikelets: Sequence[object]):
    geometry_wkt = row.get("spikelet_geometry_wkt")
    if not geometry_wkt:
        return None, None
    try:
        source_geometry = shapely_wkt.loads(str(geometry_wkt))
    except Exception:
        return None, None

    ranked = sorted(
        (
            (geometry_iou(source_geometry, item.geometry), item)
            for item in spikelets
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked:
        return None, None

    best_iou, best = ranked[0]
    second_iou = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = best_iou - second_iou
    meta = {
        "best_iou": float(best_iou),
        "second_iou": float(second_iou),
        "margin": float(margin),
    }
    if (
        best_iou < GEOMETRY_CROSSWALK_MIN_IOU
        or margin < GEOMETRY_CROSSWALK_MIN_MARGIN
    ):
        return None, {"status": "geometry_crosswalk_rejected", **meta}

    return best, {
        "status": "geometry_crosswalk",
        **meta,
        "matched_seed_hypothesis_id": str(best.seed_hypothesis_id),
    }


def resolve_spikelet_identity(
    row: Mapping[str, object],
    spikelets: Sequence[object],
) -> SpikeletIdentityResolution:
    source_id = str(row.get("spikelet_id"))
    by_seed = {str(item.seed_hypothesis_id): item for item in spikelets}

    preferred = row.get("canonical_source_spikelet_id")
    if preferred:
        preferred_id = str(preferred)
        spikelet = by_seed.get(preferred_id)
        if spikelet is not None:
            return SpikeletIdentityResolution(
                spikelet=spikelet,
                status="provenance_alias",
                source_spikelet_id=source_id,
                canonical_spikelet_id=preferred_id,
                metadata={"preferred_canonical_spikelet_id": preferred_id},
            )

    spikelet = by_seed.get(source_id)
    if spikelet is not None:
        return SpikeletIdentityResolution(
            spikelet=spikelet,
            status="exact",
            source_spikelet_id=source_id,
            canonical_spikelet_id=source_id,
            metadata={},
        )

    spikelet, crosswalk_meta = geometry_crosswalk(row, spikelets)
    if spikelet is not None:
        canonical_id = str(spikelet.seed_hypothesis_id)
        return SpikeletIdentityResolution(
            spikelet=spikelet,
            status="geometry_crosswalk",
            source_spikelet_id=source_id,
            canonical_spikelet_id=canonical_id,
            metadata={"geometry_crosswalk": crosswalk_meta},
        )

    return SpikeletIdentityResolution(
        spikelet=None,
        status="unresolved",
        source_spikelet_id=source_id,
        canonical_spikelet_id=None,
        metadata=(
            {"geometry_crosswalk": crosswalk_meta}
            if crosswalk_meta is not None
            else {}
        ),
    )


__all__ = [
    "GEOMETRY_CROSSWALK_MIN_IOU",
    "GEOMETRY_CROSSWALK_MIN_MARGIN",
    "SpikeletIdentityResolution",
    "geometry_crosswalk",
    "geometry_iou",
    "resolve_spikelet_identity",
]
