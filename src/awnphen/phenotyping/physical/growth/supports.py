"""Support-fragment construction for Unified Growth v1."""
from __future__ import annotations

from awnphen.phenotyping.physical.trajectory import (
    path_length,
    skeleton_features,
)
from shapely.geometry import LineString

from .junctions import support_junctions


def _orient_root_to_tip(raw_path, canonical_path):
    """Orient one support from the spikelet/root side toward the distal tip.

    The page transform guarantees canonical UP, so the root is the endpoint
    with larger canonical y and the distal tip is the endpoint with smaller y.
    """
    raw = [tuple(map(float, p)) for p in raw_path]
    can = [tuple(map(float, p)) for p in canonical_path]
    if len(can) >= 2 and can[0][1] < can[-1][1]:
        raw.reverse()
        can.reverse()
    return raw, can


def _hypothesis_confidence(hypothesis, evidence_by_id):
    vals = [
        float(evidence_by_id[str(eid)].confidence)
        for eid in hypothesis.evidence_ids
        if str(eid) in evidence_by_id
    ]
    return max(vals) if vals else 0.0


def _hypothesis_prediction_keys(hypothesis, evidence_by_id):
    keys = set()
    for eid in hypothesis.evidence_ids:
        evidence = evidence_by_id.get(str(eid))
        if evidence is None:
            continue
        provider = getattr(evidence.provider, "value", str(evidence.provider))
        keys.add(
            f"{provider}:{evidence.source_tile_id}:{int(evidence.source_prediction_index)}"
        )
    return tuple(sorted(keys))


def build_support_pool(awn_hypotheses, transform, evidence_by_id, *, skeleton_cache=None):
    pool = []
    for hypothesis in awn_hypotheses:
        cache_key = str(hypothesis.hypothesis_id)
        skel = None if skeleton_cache is None else skeleton_cache.get(cache_key)
        if skel is None:
            skel = skeleton_features(hypothesis.geometry)
            if skeleton_cache is not None:
                skeleton_cache[cache_key] = skel
        if len(skel["path"]) < 2:
            continue
        raw = [tuple(map(float, p)) for p in skel["path"]]
        can = [transform.raw_px_to_canonical_mm(p) for p in raw]
        raw, can = _orient_root_to_tip(raw, can)
        pool.append(
            {
                "support_hypothesis_id": str(hypothesis.hypothesis_id),
                "raw_path": raw,
                "canonical_path_mm": can,
                "canonical_line": LineString(can),
                "confidence": _hypothesis_confidence(hypothesis, evidence_by_id),
                "prediction_keys": _hypothesis_prediction_keys(hypothesis, evidence_by_id),
                "geometry": hypothesis.geometry,
                "length_mm": float(path_length(can)),
                "path_junctions": support_junctions(skel, transform),
                "_path_indices": {tuple(p): i for i, p in enumerate(raw)},
            }
        )
    return pool

__all__ = ["build_support_pool"]
