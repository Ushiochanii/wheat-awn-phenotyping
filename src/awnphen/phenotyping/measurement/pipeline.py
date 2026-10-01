"""Measurement orchestration for page-level representative normalization."""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from awnphen.phenotyping.physical.identity_bridge import (
    resolve_spikelet_identity,
)
from .root_normalization import normalize_root_to_spikelet_exit


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_root_normalization(
    *,
    repository_root: Path,
    pages: Sequence[str],
    representative_root: Path,
    output: Path,
    calibration: Mapping[str, Mapping[str, float]],
    spikelets_by_page: Mapping[str, Sequence[object]],
) -> dict:
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    page_rows = []
    removed = []
    status_counts = Counter()
    identity_bridge_counts = Counter()
    selected_total = 0
    for page in pages:
        source = _load(Path(representative_root) / page / "representative_result.json")
        reps = []
        page_removed = []
        page_status = Counter()
        cal = calibration[page]
        for original in source["representatives"]:
            row = dict(original)
            if row.get("status") != "SELECTED" or not row.get("raw_path"):
                reps.append(row)
                continue
            selected_total += 1
            resolution = resolve_spikelet_identity(
                row,
                spikelets_by_page[page],
            )
            spikelet = resolution.spikelet
            bridge_meta = {
                "status": resolution.status,
                "source_spikelet_id": resolution.source_spikelet_id,
                **dict(resolution.metadata),
            }
            if resolution.canonical_spikelet_id is not None:
                bridge_meta["canonical_spikelet_id"] = (
                    resolution.canonical_spikelet_id
                )
            row["identity_bridge"] = bridge_meta
            identity_bridge_counts[resolution.status] += 1

            if spikelet is None:
                row["root_normalization"] = {
                    "status": "spikelet_not_found",
                    "removed_mm": 0.0,
                    **dict(resolution.metadata),
                }
                page_status["spikelet_not_found"] += 1
                status_counts["spikelet_not_found"] += 1
                reps.append(row)
                continue

            canonical_spikelet_id = str(resolution.canonical_spikelet_id)
            if resolution.status != "exact":
                row["source_spikelet_id"] = resolution.source_spikelet_id
                row["spikelet_id"] = canonical_spikelet_id
            row["canonical_spikelet_id"] = canonical_spikelet_id
            normalized, meta = normalize_root_to_spikelet_exit(
                row["raw_path"],
                spikelet.geometry,
                x_period_px_5mm=float(cal["x"]),
                y_period_px_5mm=float(cal["y"]),
            )
            meta = dict(meta)
            if "geometry_crosswalk" in resolution.metadata:
                meta["geometry_crosswalk"] = resolution.metadata[
                    "geometry_crosswalk"
                ]
            status = str(meta.get("status", "unknown"))
            removed_mm = float(meta.get("removed_mm", 0.0) or 0.0)
            row["raw_path"] = [list(map(float, point)) for point in normalized]
            if normalized:
                row["root_raw_px"] = list(map(float, normalized[0]))
                row["tip_raw_px"] = list(map(float, normalized[-1]))
            if meta.get("after_mm") is not None:
                row["length_mm"] = float(meta["after_mm"])
            row["root_normalization"] = meta
            page_status[status] += 1
            status_counts[status] += 1
            if removed_mm > 0:
                page_removed.append(removed_mm)
                removed.append(removed_mm)
            reps.append(row)
        page_dir = output / page
        page_dir.mkdir()
        (page_dir / "representative_result.json").write_text(
            json.dumps(
                {"page_id": page, "representatives": reps, "candidates": source.get("candidates", [])},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        page_rows.append({
            "page_id": page,
            "selected": sum(item.get("status") == "SELECTED" for item in reps),
            "normalized": sum(
                float(item.get("root_normalization", {}).get("removed_mm", 0.0) or 0.0) > 0
                for item in reps
            ),
            "removed_mm": sum(page_removed),
            "status_counts": dict(page_status),
        })
    source_rel = Path(representative_root).relative_to(repository_root)
    summary = {
        "schema": "root_normalization_stage_v1",
        "source_representative_root": str(source_rel),
        "parameters": {
            "outside_hold_mm": 0.75,
            "sample_step_mm": 0.10,
            "tolerance_px": 1.0,
            "min_path_mm": 5.0,
        },
        "selected_representatives": selected_total,
        "normalized_representatives": len(removed),
        "status_counts": dict(status_counts),
        "identity_bridge_counts": dict(identity_bridge_counts),
        "pages": page_rows,
        "removed_mm": {
            "total": sum(removed),
            "median": statistics.median(removed) if removed else 0.0,
            "p95": float(np.percentile(removed, 95)) if removed else 0.0,
            "max": max(removed, default=0.0),
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


__all__ = ["run_root_normalization"]
