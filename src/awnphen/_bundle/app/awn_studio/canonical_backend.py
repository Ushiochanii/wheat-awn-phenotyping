"""Awn Studio product adapter over the maintained scientific Workbench pipeline."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from shapely.geometry import LineString, mapping

from awnphen.pipeline import WORKBENCH_PAGE_ID, run_workbench_pipeline

PAGE_ID = WORKBENCH_PAGE_ID


def _adapt_unified_growth_inspection(payload, *, seeds, active_ids):
    """Map Unified Growth source spikelet IDs onto editable product spikelet IDs."""
    source_records = dict((payload or {}).get("records", {}))
    records_by_canonical_source = {}
    for record in source_records.values():
        representative = record.get("representative") or {}
        canonical_source = representative.get("canonical_source_spikelet_id")
        if canonical_source is not None:
            records_by_canonical_source[str(canonical_source)] = record
    records = {}
    source_to_product = {}
    for spikelet in seeds.physical_spikelets:
        product_id = str(spikelet.physical_spikelet_id)
        if product_id not in active_ids:
            continue
        source_id = str(spikelet.seed_hypothesis_id)
        source_to_product[source_id] = product_id
        source_record = (
            source_records.get(source_id)
            or records_by_canonical_source.get(source_id)
        )
        if source_record is None:
            continue
        records[product_id] = {
            **source_record,
            "spikelet_id": product_id,
            "source_spikelet_id": source_id,
        }
    return {
        "schema": (payload or {}).get(
            "schema",
            "unified_growth_inspection_v1",
        ),
        "stages": [
            "source",
            "detection_evidence",
            "spikelet_seed",
            "trajectory_growth",
            "representative_awn",
            "measurement_path",
        ],
        "support_pool": list((payload or {}).get("support_pool", ())),
        "records": records,
        "source_to_product_spikelet": source_to_product,
    }


def run_canonical(
    *,
    source,
    output,
    model,
    weights,
    model_name,
    device,
    mm_per_px,
    progress,
    model_id=None,
    physical_closeout_runner=None,
    reconciliation_runner=None,
):
    """Run the scientific service and adapt its artifacts to Awn Studio."""
    from awnphen.phenotyping.measurement.path_simplification import (
        simplify_measurement_path,
    )

    began = time.monotonic()
    workspace = output / "canonical_workspace"
    pipeline_kwargs = dict(
        source=source,
        workspace=workspace,
        model=model,
        weights=weights,
        device=device,
        mm_per_px=mm_per_px,
        progress=progress,
    )
    if physical_closeout_runner is not None:
        pipeline_kwargs["physical_closeout_runner"] = physical_closeout_runner
    if reconciliation_runner is not None:
        pipeline_kwargs["reconciliation_runner"] = reconciliation_runner
    prepared = run_workbench_pipeline(**pipeline_kwargs)

    representatives = json.loads(
        (
            prepared.closeout["root_normalized"]
            / PAGE_ID
            / "representative_result.json"
        ).read_text(encoding="utf-8")
    )["representatives"]
    diagnostics = json.loads(
        (
            prepared.closeout["representative"]
            / PAGE_ID
            / "diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    reconstruction_summary = diagnostics.get("reconstruction_summary", {})
    orientation_diagnostics = reconstruction_summary.get(
        "orientation_diagnostics",
        {},
    )
    orientation = {
        "rotation_deg": float(
            reconstruction_summary.get("orientation_rotation_deg", 0.0)
        ),
        "polarity_flipped": bool(
            reconstruction_summary.get("polarity_flipped", False)
        ),
        "polarity_confidence": float(
            reconstruction_summary.get("polarity_confidence", 0.0)
        ),
        "axis_concentration": float(
            reconstruction_summary.get("axis_concentration", 0.0)
        ),
        "policy": orientation_diagnostics.get("policy"),
    }

    selected_by_spikelet = {
        row["spikelet_id"]: row
        for row in representatives
        if row.get("status") == "SELECTED"
        and len(row.get("raw_path", ())) >= 2
    }
    active = {
        str(value)
        for value in prepared.cleanup.active_physical_spikelet_ids
    }
    inspection = _adapt_unified_growth_inspection(
        prepared.inspection,
        seeds=prepared.seeds,
        active_ids=active,
    )

    groups = []
    for spikelet in prepared.seeds.physical_spikelets:
        if str(spikelet.physical_spikelet_id) not in active:
            continue
        geometry = spikelet.geometry
        if geometry.geom_type == "MultiPolygon":
            geometry = max(geometry.geoms, key=lambda item: item.area)
        if geometry.geom_type != "Polygon" or geometry.is_empty:
            continue
        representative = selected_by_spikelet.get(
            str(spikelet.seed_hypothesis_id)
        )
        raw_line = representative.get("raw_path", []) if representative else []
        line = simplify_measurement_path(raw_line, tolerance_px=1.0)
        groups.append(
            dict(
                uid=str(spikelet.physical_spikelet_id),
                name=str(len(groups) + 1),
                polygon=[
                    list(map(float, point))
                    for point in list(
                        geometry.simplify(
                            1.5,
                            preserve_topology=True,
                        ).exterior.coords
                    )[:-1]
                ],
                line=[list(map(float, point)) for point in line],
                origin="automatic",
                modified=False,
                confirmed=False,
                modelAwnId=(
                    representative.get("candidate_id")
                    if representative
                    else None
                ),
            )
        )

    candidate_masks = []
    for product_spikelet_id, record in inspection["records"].items():
        for branch_index, branch in enumerate(
            record.get("_candidate_branches", ())
        ):
            seed = branch.get("seed", {})
            seed_path = seed.get("raw_path", [])
            seed_id = str(
                seed.get(
                    "support_hypothesis_id",
                    f"seed-{branch_index}",
                )
            )
            if len(seed_path) >= 2:
                geometry = LineString(seed_path).buffer(
                    2.0,
                    cap_style=1,
                    join_style=1,
                )
                candidate_masks.append(
                    dict(
                        id=(
                            f"{product_spikelet_id}:{branch_index}:"
                            f"seed:{seed_id}"
                        ),
                        class_id=0,
                        geometry=mapping(geometry),
                        spikelet_id=str(product_spikelet_id),
                        branch_index=branch_index,
                        growth_stage="seed",
                        hop=0,
                        support_hypothesis_id=seed_id,
                    )
                )
            for step in branch.get("hops", ()):
                raw_path = step.get("raw_path", [])
                if len(raw_path) < 2:
                    continue
                hop = int(step.get("hop", 0))
                support_id = str(
                    step.get(
                        "support_hypothesis_id",
                        f"hop-{hop}",
                    )
                )
                geometry = LineString(raw_path).buffer(
                    2.0,
                    cap_style=1,
                    join_style=1,
                )
                candidate_masks.append(
                    dict(
                        id=(
                            f"{product_spikelet_id}:{branch_index}:"
                            f"hop:{hop}:{support_id}"
                        ),
                        class_id=0,
                        geometry=mapping(geometry),
                        spikelet_id=str(product_spikelet_id),
                        branch_index=branch_index,
                        growth_stage="hop",
                        hop=hop,
                        support_hypothesis_id=support_id,
                    )
                )

    representative_masks = []
    source_to_product = inspection.get(
        "source_to_product_spikelet",
        {},
    )
    for row in selected_by_spikelet.values():
        geometry = LineString(row["raw_path"]).buffer(
            2.0,
            cap_style=1,
            join_style=1,
        )
        source_spikelet_id = str(row.get("spikelet_id"))
        representative_masks.append(
            dict(
                id=str(row.get("candidate_id")),
                class_id=0,
                geometry=mapping(geometry),
                spikelet_id=str(
                    source_to_product.get(
                        source_spikelet_id,
                        source_spikelet_id,
                    )
                ),
                growth_stage="representative",
            )
        )

    result = dict(
        groups=groups,
        model=model_name,
        model_id=model_id,
        weights_sha256=hashlib.sha256(
            Path(weights).read_bytes()
        ).hexdigest(),
        layers=dict(
            raw=prepared.raw_masks,
            candidates=candidate_masks,
            representatives=representative_masks,
        ),
        source_sha256=prepared.source_sha256,
        pipeline="awnphen unified_growth_v1 physical closeout",
        orientation=orientation,
        path_simplification="DP1 measurement path; tolerance 1 px",
        pipeline_stages=[
            "detection_evidence",
            "high_overlap_awn_compaction",
            "spikelet_reconciliation_and_cleanup",
            "spikelet_axis_orientation_normalization",
            "provisional_multi_seed_discovery",
            "constrained_trajectory_growth",
            "competitive_fragment_ownership",
            "representative_branch_selection",
            "root_normalization",
        ],
        inspection=inspection,
        device=str(device),
        seconds=round(time.monotonic() - began, 2),
        tile_count=prepared.tile_count,
        evidence_count=len(prepared.evidence.evidence),
        hypothesis_count=len(prepared.reconciliation.hypotheses),
        awn_masks=len(candidate_masks),
        spikelet_masks=len(groups),
        path_count=sum(len(group["line"]) >= 2 for group in groups),
        scale=(
            "UI manual calibration supplied to canonical physical pipeline"
        ),
        calibration_mm_per_px=float(mm_per_px),
    )
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )
    return result
