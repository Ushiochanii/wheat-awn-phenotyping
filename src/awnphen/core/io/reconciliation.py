"""Persistence helpers for Phase 3 reconciliation results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from shapely import wkb

from awnphen.core.domain.physical import HypothesisStatus, InstanceHypothesis
from awnphen.core.domain.physical_provenance import EvidenceId, OperationProvenance, SnapshotId
from awnphen.phenotyping.detection.reconciliation import (
    RECONCILIATION_FILE_SCHEMA,
    PairDecision,
    PairDecisionStatus,
    PairFeatures,
    ReconciliationResult,
)


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


def reconciliation_result_to_dict(
    result: ReconciliationResult,
) -> dict[str, Any]:
    return {
        "file_schema": RECONCILIATION_FILE_SCHEMA,
        "page_id": result.page_id,
        "snapshot_id": str(result.snapshot_id),
        "source_evidence_ids": [
            str(value) for value in result.source_evidence_ids
        ],
        "config_payload": _jsonable(result.config_payload),
        "config_sha256": result.config_sha256,
        "blocked_strong_pair_ids": list(result.blocked_strong_pair_ids),
        "pair_decisions": [
            {
                "pair_id": item.pair_id,
                "snapshot_id": str(item.snapshot_id),
                "page_id": item.page_id,
                "class_name": item.class_name,
                "left_evidence_id": str(item.left_evidence_id),
                "right_evidence_id": str(item.right_evidence_id),
                "status": item.status.value,
                "reason": item.reason,
                "strength": item.strength,
                "features": item.features.to_dict(),
                "provenance": item.provenance.to_dict(),
            }
            for item in result.pair_decisions
        ],
        "hypotheses": [
            {
                "hypothesis_id": str(item.hypothesis_id),
                "snapshot_id": str(item.snapshot_id),
                "page_id": item.page_id,
                "class_id": item.class_id,
                "class_name": item.class_name,
                "evidence_ids": [
                    str(value) for value in item.evidence_ids
                ],
                "geometry_wkb_hex": item.geometry.wkb_hex,
                "status": item.status.value,
                "provenance": [
                    record.to_dict() for record in item.provenance
                ],
            }
            for item in result.hypotheses
        ],
        "hypothesis_diagnostics": _jsonable(
            result.hypothesis_diagnostics
        ),
    }


def reconciliation_result_from_dict(
    payload: Mapping[str, Any],
) -> ReconciliationResult:
    if payload.get("file_schema") != RECONCILIATION_FILE_SCHEMA:
        raise ValueError(
            f"unsupported reconciliation schema: {payload.get('file_schema')}"
        )
    snapshot_id = SnapshotId(str(payload["snapshot_id"]))
    page_id = str(payload["page_id"])

    pair_decisions = []
    for item in payload.get("pair_decisions", ()):
        features = PairFeatures(
            **{
                key: value
                for key, value in dict(item["features"]).items()
            }
        )
        pair_decisions.append(
            PairDecision(
                pair_id=str(item["pair_id"]),
                snapshot_id=SnapshotId(str(item["snapshot_id"])),
                page_id=str(item["page_id"]),
                class_name=str(item["class_name"]),
                left_evidence_id=EvidenceId(
                    str(item["left_evidence_id"])
                ),
                right_evidence_id=EvidenceId(
                    str(item["right_evidence_id"])
                ),
                status=PairDecisionStatus(str(item["status"])),
                reason=str(item["reason"]),
                strength=float(item["strength"]),
                features=features,
                provenance=_provenance_from_dict(item["provenance"]),
            )
        )

    hypotheses = []
    for item in payload.get("hypotheses", ()):
        provenance = tuple(
            _provenance_from_dict(value)
            for value in item.get("provenance", ())
        )
        hypothesis = InstanceHypothesis.create(
            snapshot_id=SnapshotId(str(item["snapshot_id"])),
            page_id=str(item["page_id"]),
            class_id=int(item["class_id"]),
            class_name=str(item["class_name"]),
            evidence_ids=tuple(
                EvidenceId(str(value))
                for value in item["evidence_ids"]
            ),
            geometry=wkb.loads(
                str(item["geometry_wkb_hex"]), hex=True
            ),
            status=HypothesisStatus(str(item["status"])),
            provenance=provenance,
        )
        if str(hypothesis.hypothesis_id) != str(item["hypothesis_id"]):
            raise ValueError(
                "stored hypothesis_id does not match evidence membership"
            )
        hypotheses.append(hypothesis)

    return ReconciliationResult(
        page_id=page_id,
        snapshot_id=snapshot_id,
        source_evidence_ids=tuple(
            EvidenceId(str(value))
            for value in payload["source_evidence_ids"]
        ),
        pair_decisions=tuple(pair_decisions),
        hypotheses=tuple(hypotheses),
        hypothesis_diagnostics=dict(
            payload["hypothesis_diagnostics"]
        ),
        config_payload=dict(payload["config_payload"]),
        config_sha256=str(payload["config_sha256"]),
        blocked_strong_pair_ids=tuple(
            str(value)
            for value in payload.get("blocked_strong_pair_ids", ())
        ),
    )


def write_reconciliation_result(
    result: ReconciliationResult,
    path: str | Path,
) -> Path:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            reconciliation_result_to_dict(result),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def read_reconciliation_result(
    path: str | Path,
) -> ReconciliationResult:
    path = Path(path)
    return reconciliation_result_from_dict(
        json.loads(path.read_text(encoding="utf-8"))
    )


__all__ = [
    "read_reconciliation_result",
    "reconciliation_result_from_dict",
    "reconciliation_result_to_dict",
    "write_reconciliation_result",
]
