"""Persistence helpers for physical spikelet cleanup."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from awnphen.core.domain.physical_provenance import (
    OperationProvenance,
    PhysicalSpikeletId,
    SnapshotId,
)
from awnphen.phenotyping.physical.spikelet_cleanup import (
    PhysicalSpikeletCleanupDecision,
    PhysicalSpikeletCleanupResult,
    SpikeletCleanupStatus,
)

SPIKELET_CLEANUP_FILE_SCHEMA = "awnphen_spikelet_cleanup_file_v1"


def _prov_from_dict(payload: Mapping[str, Any]) -> OperationProvenance:
    record = OperationProvenance(
        operation=str(payload["operation"]),
        implementation=str(payload["implementation"]),
        input_ids=tuple(str(v) for v in payload.get("input_ids", ())),
        output_id=payload.get("output_id"),
        status=str(payload["status"]),
        parameters=dict(payload.get("parameters", {})),
        evidence=dict(payload.get("evidence", {})),
    )
    stored_id = payload.get("provenance_id")
    if stored_id is not None and str(stored_id) != record.provenance_id:
        raise ValueError("stored provenance_id does not match provenance content")
    return record


def spikelet_cleanup_result_to_dict(
    result: PhysicalSpikeletCleanupResult,
) -> dict[str, Any]:
    return {
        "file_schema": SPIKELET_CLEANUP_FILE_SCHEMA,
        "page_id": result.page_id,
        "snapshot_id": str(result.snapshot_id),
        "source_physical_spikelet_ids": [
            str(value) for value in result.source_physical_spikelet_ids
        ],
        "active_physical_spikelet_ids": [
            str(value) for value in result.active_physical_spikelet_ids
        ],
        "rejected_physical_spikelet_ids": [
            str(value) for value in result.rejected_physical_spikelet_ids
        ],
        "decisions": [
            {
                "decision_id": item.decision_id,
                "snapshot_id": str(item.snapshot_id),
                "page_id": item.page_id,
                "physical_spikelet_id": str(item.physical_spikelet_id),
                "status": item.status.value,
                "source_confidence": item.source_confidence,
                "area_px2": item.area_px2,
                "neighbor_spikelet_ids": [
                    str(value) for value in item.neighbor_spikelet_ids
                ],
                "neighbor_distances_px": list(item.neighbor_distances_px),
                "neighbor_areas_px2": list(item.neighbor_areas_px2),
                "neighbor_area_median_px2": item.neighbor_area_median_px2,
                "area_ratio_to_neighbor_median": (
                    item.area_ratio_to_neighbor_median
                ),
                "nearest_distance_px": item.nearest_distance_px,
                "normalized_nearest_distance": (
                    item.normalized_nearest_distance
                ),
                "rotated_aspect": item.rotated_aspect,
                "solidity": item.solidity,
                "extent": item.extent,
                "compactness": item.compactness,
                "isolated_small_suspicious": (
                    item.isolated_small_suspicious
                ),
                "provenance": [
                    record.to_dict() for record in item.provenance
                ],
            }
            for item in result.decisions
        ],
    }


def spikelet_cleanup_result_from_dict(
    payload: Mapping[str, Any],
) -> PhysicalSpikeletCleanupResult:
    if payload.get("file_schema") != SPIKELET_CLEANUP_FILE_SCHEMA:
        raise ValueError(
            f"unsupported spikelet cleanup schema: {payload.get('file_schema')}"
        )
    decisions = []
    for item in payload.get("decisions", ()):
        decisions.append(
            PhysicalSpikeletCleanupDecision(
                decision_id=str(item["decision_id"]),
                snapshot_id=SnapshotId(str(item["snapshot_id"])),
                page_id=str(item["page_id"]),
                physical_spikelet_id=PhysicalSpikeletId(
                    str(item["physical_spikelet_id"])
                ),
                status=SpikeletCleanupStatus(str(item["status"])),
                source_confidence=float(item["source_confidence"]),
                area_px2=float(item["area_px2"]),
                neighbor_spikelet_ids=tuple(
                    PhysicalSpikeletId(str(value))
                    for value in item.get("neighbor_spikelet_ids", ())
                ),
                neighbor_distances_px=tuple(
                    float(value)
                    for value in item.get("neighbor_distances_px", ())
                ),
                neighbor_areas_px2=tuple(
                    float(value)
                    for value in item.get("neighbor_areas_px2", ())
                ),
                neighbor_area_median_px2=(
                    None
                    if item.get("neighbor_area_median_px2") is None
                    else float(item["neighbor_area_median_px2"])
                ),
                area_ratio_to_neighbor_median=(
                    None
                    if item.get("area_ratio_to_neighbor_median") is None
                    else float(item["area_ratio_to_neighbor_median"])
                ),
                nearest_distance_px=(
                    None
                    if item.get("nearest_distance_px") is None
                    else float(item["nearest_distance_px"])
                ),
                normalized_nearest_distance=(
                    None
                    if item.get("normalized_nearest_distance") is None
                    else float(item["normalized_nearest_distance"])
                ),
                rotated_aspect=float(item["rotated_aspect"]),
                solidity=float(item["solidity"]),
                extent=float(item["extent"]),
                compactness=float(item["compactness"]),
                isolated_small_suspicious=bool(
                    item["isolated_small_suspicious"]
                ),
                provenance=tuple(
                    _prov_from_dict(value)
                    for value in item.get("provenance", ())
                ),
            )
        )

    return PhysicalSpikeletCleanupResult(
        page_id=str(payload["page_id"]),
        snapshot_id=SnapshotId(str(payload["snapshot_id"])),
        source_physical_spikelet_ids=tuple(
            PhysicalSpikeletId(str(value))
            for value in payload.get("source_physical_spikelet_ids", ())
        ),
        decisions=tuple(decisions),
        active_physical_spikelet_ids=tuple(
            PhysicalSpikeletId(str(value))
            for value in payload.get("active_physical_spikelet_ids", ())
        ),
        rejected_physical_spikelet_ids=tuple(
            PhysicalSpikeletId(str(value))
            for value in payload.get("rejected_physical_spikelet_ids", ())
        ),
    )


def write_spikelet_cleanup_result(
    result: PhysicalSpikeletCleanupResult,
    path: str | Path,
) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            spikelet_cleanup_result_to_dict(result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_spikelet_cleanup_result(
    path: str | Path,
) -> PhysicalSpikeletCleanupResult:
    path = Path(path)
    return spikelet_cleanup_result_from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )


__all__ = [
    "SPIKELET_CLEANUP_FILE_SCHEMA",
    "read_spikelet_cleanup_result",
    "spikelet_cleanup_result_from_dict",
    "spikelet_cleanup_result_to_dict",
    "write_spikelet_cleanup_result",
]
