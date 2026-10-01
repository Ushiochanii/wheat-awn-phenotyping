"""Inference provenance and deterministic artifact fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .ids import SnapshotId, make_snapshot_id


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON-compatible data independently of mapping key order."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class InferenceProvenance:
    """Immutable provenance for one page-level prediction snapshot."""

    page_id: str
    source_sha256: str
    weights_sha256: str
    prediction_records_sha256: str
    input_size: int
    stride: int
    nms_iou: float
    confidence_inference: float
    first_stage_merge: Mapping[str, Any]
    frozen_postprocess: Mapping[str, Any]
    ground_truth_used: bool
    frozen_parameters_changed_for_page: bool

    def snapshot_payload(self) -> dict[str, Any]:
        """Return the immutable fields that define the analysis snapshot."""
        return {
            "schema": "wheat_awn_inference_snapshot_v1",
            "page_id": self.page_id,
            "source_sha256": self.source_sha256,
            "weights_sha256": self.weights_sha256,
            "prediction_records_sha256": self.prediction_records_sha256,
            "input_size": self.input_size,
            "stride": self.stride,
            "nms_iou": self.nms_iou,
            "confidence_inference": self.confidence_inference,
            "first_stage_merge": dict(self.first_stage_merge),
            "frozen_postprocess": dict(self.frozen_postprocess),
            "ground_truth_used": self.ground_truth_used,
            "frozen_parameters_changed_for_page": (
                self.frozen_parameters_changed_for_page
            ),
        }

    @property
    def snapshot_id(self) -> SnapshotId:
        return make_snapshot_id(self.snapshot_payload())


_REQUIRED_PAYLOAD_KEYS = (
    "page",
    "source_sha256",
    "weights_sha256",
    "input_size",
    "stride",
    "nms_iou",
    "confidence_inference",
    "first_stage_merge",
    "frozen_postprocess",
    "predictions",
)


def inference_provenance_from_payload(
    payload: Mapping[str, Any],
) -> InferenceProvenance:
    """Build provenance from one historical sliding-window inference payload."""
    missing = [
        key
        for key in _REQUIRED_PAYLOAD_KEYS
        if key not in payload
    ]
    if missing:
        raise ValueError(
            "inference payload missing required provenance keys: "
            + ", ".join(missing)
        )

    predictions = payload["predictions"]
    if not isinstance(predictions, list):
        raise ValueError("inference payload predictions must be a list")

    return InferenceProvenance(
        page_id=str(payload["page"]),
        source_sha256=str(payload["source_sha256"]),
        weights_sha256=str(payload["weights_sha256"]),
        prediction_records_sha256=canonical_json_sha256(predictions),
        input_size=int(payload["input_size"]),
        stride=int(payload["stride"]),
        nms_iou=float(payload["nms_iou"]),
        confidence_inference=float(payload["confidence_inference"]),
        first_stage_merge=dict(payload["first_stage_merge"]),
        frozen_postprocess=dict(payload["frozen_postprocess"]),
        ground_truth_used=bool(payload.get("ground_truth_used", False)),
        frozen_parameters_changed_for_page=bool(
            payload.get("frozen_parameters_changed_for_page", False)
        ),
    )


@dataclass(frozen=True)
class OperationProvenance:
    """Auditable record of one structural/domain operation."""

    operation: str
    implementation: str
    input_ids: tuple[str, ...]
    output_id: str | None
    status: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "implementation": self.implementation,
            "input_ids": list(self.input_ids),
            "output_id": self.output_id,
            "status": self.status,
            "parameters": dict(self.parameters),
            "evidence": dict(self.evidence),
        }

    @property
    def provenance_id(self) -> str:
        return "prov_" + canonical_json_sha256(self.payload())[:20]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance_id": self.provenance_id,
            **self.payload(),
        }
