"""Persistence helpers for Phase 4A physical seeds."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from shapely import wkb

from awnphen.core.domain.physical import PhysicalAwn, PhysicalSpikelet
from awnphen.core.domain.physical_provenance import (
    EvidenceId,
    HypothesisId,
    OperationProvenance,
    SnapshotId,
)
from awnphen.phenotyping.physical.contracts import PhysicalSeedResult

PHYSICAL_SEED_FILE_SCHEMA = "awnphen_physical_seed_file_v1"


def _provenance_from_dict(payload: Mapping[str, Any]) -> OperationProvenance:
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


def _entity_to_dict(entity: PhysicalAwn | PhysicalSpikelet) -> dict[str, Any]:
    entity_id = (
        str(entity.physical_awn_id)
        if isinstance(entity, PhysicalAwn)
        else str(entity.physical_spikelet_id)
    )
    return {
        "physical_entity_id": entity_id,
        "snapshot_id": str(entity.snapshot_id),
        "page_id": entity.page_id,
        "seed_hypothesis_id": str(entity.seed_hypothesis_id),
        "source_hypothesis_ids": [
            str(value) for value in entity.source_hypothesis_ids
        ],
        "source_evidence_ids": [
            str(value) for value in entity.source_evidence_ids
        ],
        "geometry_wkb_hex": entity.geometry.wkb_hex,
        "provenance": [item.to_dict() for item in entity.provenance],
    }


def physical_seed_result_to_dict(
    result: PhysicalSeedResult,
) -> dict[str, Any]:
    return {
        "file_schema": PHYSICAL_SEED_FILE_SCHEMA,
        "page_id": result.page_id,
        "snapshot_id": str(result.snapshot_id),
        "source_hypothesis_ids": [
            str(value) for value in result.source_hypothesis_ids
        ],
        "physical_awns": [
            _entity_to_dict(item) for item in result.physical_awns
        ],
        "physical_spikelets": [
            _entity_to_dict(item) for item in result.physical_spikelets
        ],
        "unresolved_hypothesis_ids": [
            str(value) for value in result.unresolved_hypothesis_ids
        ],
    }


def _awn_from_dict(item: Mapping[str, Any]) -> PhysicalAwn:
    entity = PhysicalAwn.create(
        snapshot_id=SnapshotId(str(item["snapshot_id"])),
        page_id=str(item["page_id"]),
        seed_hypothesis_id=HypothesisId(str(item["seed_hypothesis_id"])),
        source_hypothesis_ids=tuple(
            HypothesisId(str(value))
            for value in item["source_hypothesis_ids"]
        ),
        source_evidence_ids=tuple(
            EvidenceId(str(value))
            for value in item["source_evidence_ids"]
        ),
        geometry=wkb.loads(str(item["geometry_wkb_hex"]), hex=True),
        provenance=tuple(
            _provenance_from_dict(value)
            for value in item.get("provenance", ())
        ),
    )
    if str(entity.physical_awn_id) != str(item["physical_entity_id"]):
        raise ValueError("stored PhysicalAwn ID does not match seed identity")
    return entity


def _spikelet_from_dict(item: Mapping[str, Any]) -> PhysicalSpikelet:
    entity = PhysicalSpikelet.create(
        snapshot_id=SnapshotId(str(item["snapshot_id"])),
        page_id=str(item["page_id"]),
        seed_hypothesis_id=HypothesisId(str(item["seed_hypothesis_id"])),
        source_hypothesis_ids=tuple(
            HypothesisId(str(value))
            for value in item["source_hypothesis_ids"]
        ),
        source_evidence_ids=tuple(
            EvidenceId(str(value))
            for value in item["source_evidence_ids"]
        ),
        geometry=wkb.loads(str(item["geometry_wkb_hex"]), hex=True),
        provenance=tuple(
            _provenance_from_dict(value)
            for value in item.get("provenance", ())
        ),
    )
    if str(entity.physical_spikelet_id) != str(item["physical_entity_id"]):
        raise ValueError(
            "stored PhysicalSpikelet ID does not match seed identity"
        )
    return entity


def physical_seed_result_from_dict(
    payload: Mapping[str, Any],
) -> PhysicalSeedResult:
    if payload.get("file_schema") != PHYSICAL_SEED_FILE_SCHEMA:
        raise ValueError(
            f"unsupported physical seed schema: {payload.get('file_schema')}"
        )
    return PhysicalSeedResult(
        page_id=str(payload["page_id"]),
        snapshot_id=SnapshotId(str(payload["snapshot_id"])),
        source_hypothesis_ids=tuple(
            HypothesisId(str(value))
            for value in payload["source_hypothesis_ids"]
        ),
        physical_awns=tuple(
            _awn_from_dict(value)
            for value in payload.get("physical_awns", ())
        ),
        physical_spikelets=tuple(
            _spikelet_from_dict(value)
            for value in payload.get("physical_spikelets", ())
        ),
        unresolved_hypothesis_ids=tuple(
            HypothesisId(str(value))
            for value in payload.get("unresolved_hypothesis_ids", ())
        ),
    )


def write_physical_seed_result(
    result: PhysicalSeedResult,
    path: str | Path,
) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            physical_seed_result_to_dict(result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_physical_seed_result(path: str | Path) -> PhysicalSeedResult:
    path = Path(path)
    return physical_seed_result_from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )


__all__ = [
    "PHYSICAL_SEED_FILE_SCHEMA",
    "physical_seed_result_from_dict",
    "physical_seed_result_to_dict",
    "read_physical_seed_result",
    "write_physical_seed_result",
]
