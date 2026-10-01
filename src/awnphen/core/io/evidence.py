"""Persistence for canonical Phase 2 evidence snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from shapely import wkb

from awnphen.phenotyping.detection.acquisition import EVIDENCE_SNAPSHOT_SCHEMA, EvidenceAcquisitionResult
from awnphen.core.domain.physical import DetectionEvidence, EvidenceProvider
from awnphen.core.domain.physical_provenance import OperationProvenance, SnapshotId, make_snapshot_id


EVIDENCE_FILE_SCHEMA = "awnphen_detection_evidence_file_v1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


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


def evidence_result_to_dict(
    result: EvidenceAcquisitionResult,
) -> dict[str, Any]:
    return {
        "file_schema": EVIDENCE_FILE_SCHEMA,
        "snapshot_schema": EVIDENCE_SNAPSHOT_SCHEMA,
        "page_id": result.page_id,
        "source_sha256": result.source_sha256,
        "snapshot_id": str(result.snapshot_id),
        "raw_observations_sha256": result.raw_observations_sha256,
        "providers": [item.value for item in result.providers],
        "provider_provenance": _jsonable(result.provider_provenance),
        "evidence": [
            {
                "evidence_id": str(item.evidence_id),
                "snapshot_id": str(item.snapshot_id),
                "page_id": item.page_id,
                "class_id": item.class_id,
                "class_name": item.class_name,
                "geometry_wkb_hex": item.geometry.wkb_hex,
                "confidence": item.confidence,
                "provider": item.provider.value,
                "source_tile_id": item.source_tile_id,
                "source_prediction_index": item.source_prediction_index,
                "source_component_index": item.source_component_index,
                "provenance": [
                    record.to_dict()
                    for record in item.provenance
                ],
            }
            for item in result.evidence
        ],
    }


def evidence_result_from_dict(
    payload: Mapping[str, Any],
) -> EvidenceAcquisitionResult:
    if payload.get("file_schema") != EVIDENCE_FILE_SCHEMA:
        raise ValueError(
            f"unsupported evidence file schema: {payload.get('file_schema')}"
        )
    if payload.get("snapshot_schema") != EVIDENCE_SNAPSHOT_SCHEMA:
        raise ValueError(
            "evidence snapshot schema does not match current contract"
        )

    page_id = str(payload["page_id"])
    source_sha256 = str(payload["source_sha256"])
    raw_hash = str(payload["raw_observations_sha256"])
    provider_provenance = {
        str(key): dict(value)
        for key, value in payload["provider_provenance"].items()
    }
    providers = tuple(
        EvidenceProvider(str(value))
        for value in payload["providers"]
    )

    expected_snapshot_id = make_snapshot_id(
        {
            "schema": EVIDENCE_SNAPSHOT_SCHEMA,
            "page_id": page_id,
            "source_sha256": source_sha256,
            "providers": sorted(
                [
                    {
                        "provider": provider.value,
                        "provenance": provider_provenance[provider.value],
                    }
                    for provider in providers
                ],
                key=lambda item: item["provider"],
            ),
            "raw_observations_sha256": raw_hash,
        }
    )
    if str(expected_snapshot_id) != str(payload["snapshot_id"]):
        raise ValueError("stored snapshot_id does not match snapshot content")

    evidence = []
    for record in payload["evidence"]:
        provenance = tuple(
            _provenance_from_dict(item)
            for item in record.get("provenance", ())
        )
        item = DetectionEvidence.create(
            snapshot_id=SnapshotId(str(payload["snapshot_id"])),
            page_id=str(record["page_id"]),
            class_id=int(record["class_id"]),
            class_name=str(record["class_name"]),
            geometry=wkb.loads(str(record["geometry_wkb_hex"]), hex=True),
            confidence=float(record["confidence"]),
            provider=str(record["provider"]),
            source_tile_id=str(record["source_tile_id"]),
            source_prediction_index=int(record["source_prediction_index"]),
            source_component_index=int(record.get("source_component_index", 0)),
            provenance=provenance,
        )
        if str(item.evidence_id) != str(record["evidence_id"]):
            raise ValueError(
                "stored evidence_id does not match immutable evidence identity"
            )
        if str(record["snapshot_id"]) != str(payload["snapshot_id"]):
            raise ValueError("evidence record snapshot_id mismatch")
        evidence.append(item)

    return EvidenceAcquisitionResult(
        page_id=page_id,
        source_sha256=source_sha256,
        snapshot_id=SnapshotId(str(payload["snapshot_id"])),
        raw_observations_sha256=raw_hash,
        providers=providers,
        provider_provenance=provider_provenance,
        evidence=tuple(evidence),
    )


def write_evidence_snapshot(
    result: EvidenceAcquisitionResult,
    path: str | Path,
) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            evidence_result_to_dict(result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_evidence_snapshot(
    path: str | Path,
) -> EvidenceAcquisitionResult:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return evidence_result_from_dict(payload)


__all__ = [
    "EVIDENCE_FILE_SCHEMA",
    "evidence_result_from_dict",
    "evidence_result_to_dict",
    "read_evidence_snapshot",
    "write_evidence_snapshot",
]
