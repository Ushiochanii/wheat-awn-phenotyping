"""Current physical closeout orchestration using Unified Growth v1.

This module is the maintained physical closeout entry. Historical physical
closeout implementations are retired under archive/source_history/ and are not
part of the production package.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from awnphen.core.io.evidence import read_evidence_snapshot
from awnphen.core.io.reconstruction import read_physical_seed_result
from awnphen.core.io.spikelet_cleanup import read_spikelet_cleanup_result
from awnphen.phenotyping.measurement.pipeline import (
    run_root_normalization,
)
from awnphen.phenotyping.physical.spikelet_overrides import (
    load_forced_spikelet_attachments,
)
from awnphen.phenotyping.physical.growth import (
    DEFAULT_UNIFIED_GROWTH_CONFIG,
    run_unified_growth_page,
)


def _save(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_physical_closeout(
    *,
    repository_root: Path,
    pages: Sequence[str],
    phase2_root: Path,
    seed_root: Path,
    cleanup_root: Path,
    output_root: Path,
    calibration: Mapping[str, Mapping[str, float]],
    phase3_root: Path | None = None,
    lowconf_main_root: Path | None = None,
    lowconf_tail_root: Path | None = None,
    inspection_sink=None,
    page_runner=None,
) -> dict[str, Path]:
    """Run the maintained Unified Growth closeout through root normalization.

    The three legacy-only arguments phase3_root, lowconf_main_root and
    lowconf_tail_root are accepted for call-site compatibility but are not
    used by the Unified Growth route.
    """
    runner = page_runner or run_unified_growth_page
    root = Path(repository_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    pages = tuple(str(page) for page in pages)

    representative = output_root / "01_unified_growth_representatives"
    rootnorm = output_root / "02_root_normalized"
    manifest = output_root / "_unified_growth_manifest.json"

    if representative.exists():
        raise FileExistsError(representative)
    representative.mkdir(parents=True)

    page_summaries: list[dict[str, object]] = []
    for page in pages:
        evidence = read_evidence_snapshot(
            Path(phase2_root) / page / "evidence_snapshot.json"
        )
        forced_attachments = load_forced_spikelet_attachments(
            root
            / "data/ground_truth/phenotype/physical_spikelet_attachment_overrides.json",
            page,
        )
        page_inspection_sink = (
            None
            if inspection_sink is None
            else lambda payload, page_id=page: inspection_sink(page_id, payload)
        )
        result = runner(
            evidence,
            page,
            calibration=calibration,
            forced_spikelet_attachments=forced_attachments,
            inspection_sink=page_inspection_sink,
        )

        page_dir = representative / page
        page_dir.mkdir(parents=True)
        _save(
            page_dir / "representative_result.json",
            {
                "page_id": page,
                "schema": "unified_growth_v1_representatives",
                "algorithm": "unified_growth_v1",
                "parameters": DEFAULT_UNIFIED_GROWTH_CONFIG.to_dict(),
                "representatives": result["representatives"],
            },
        )
        _save(
            page_dir / "diagnostics.json",
            {
                "page_id": page,
                "schema": "unified_growth_v1_diagnostics",
                "algorithm": "unified_growth_v1",
                "parameters": DEFAULT_UNIFIED_GROWTH_CONFIG.to_dict(),
                **{
                    key: value
                    for key, value in result.items()
                    if key != "representatives"
                },
            },
        )

        page_summaries.append(
            {
                "page_id": page,
                "raw_awn_count": result["raw_awn_count"],
                "compacted_awn_hypothesis_count": result[
                    "compacted_awn_hypothesis_count"
                ],
                "primary_spikelet_count": result["primary_spikelet_count"],
                "spikelets_with_seed": result["spikelets_with_seed"],
                "provisional_seed_count": result["provisional_seed_count"],
                "representative_count": result["representative_count"],
                "growth_hops": result["growth_hops"],
                "representatives_with_growth": result[
                    "representatives_with_growth"
                ],
                "timing": result["timing"],
            }
        )

    _save(
        representative / "summary.json",
        {
            "schema": "unified_growth_v1_closeout_summary",
            "algorithm": "unified_growth_v1",
            "pages": page_summaries,
            "totals": {
                "pages": len(page_summaries),
                "representatives": sum(
                    int(row["representative_count"]) for row in page_summaries
                ),
                "growth_hops": sum(
                    int(row["growth_hops"]) for row in page_summaries
                ),
                "provisional_seeds": sum(
                    int(row["provisional_seed_count"]) for row in page_summaries
                ),
            },
        },
    )

    spikelets_by_page = {}
    for page in pages:
        seeds = read_physical_seed_result(
            Path(seed_root) / page / "physical_seed_result.json"
        )
        cleanup = read_spikelet_cleanup_result(
            Path(cleanup_root) / page / "spikelet_cleanup_result.json"
        )
        active = {
            str(value) for value in cleanup.active_physical_spikelet_ids
        }
        spikelets_by_page[page] = tuple(
            item
            for item in seeds.physical_spikelets
            if str(item.physical_spikelet_id) in active
        )

    run_root_normalization(
        repository_root=root,
        pages=pages,
        representative_root=representative,
        output=rootnorm,
        calibration=calibration,
        spikelets_by_page=spikelets_by_page,
    )

    _save(
        manifest,
        {
            "schema": "unified_growth_v1_pipeline_manifest",
            "current_route": "unified_growth_v1",
            "physical_route": [
                "detection_evidence",
                "high_overlap_awn_compaction",
                "spikelet_reconciliation_and_cleanup",
                "provisional_multi_seed_discovery",
                "constrained_trajectory_growth",
                "competitive_fragment_ownership",
                "representative_branch_selection",
                "root_normalization",
            ],
            "parameters": DEFAULT_UNIFIED_GROWTH_CONFIG.to_dict(),
            "historical_archive": (
                "archive/source_history/physical_closeout_20260925/"
            ),
        },
    )

    return {
        "representative": representative,
        "root_normalized": rootnorm,
        "framework_manifest": manifest,
    }


__all__ = ["run_physical_closeout"]
