"""Stable identifiers and immutable provenance for the next phenotyping pipeline.

This module is intentionally independent from the legacy awnphen package.
During parallel development awnphen_next must describe its own objects without
importing legacy domain identities.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, NewType

SnapshotId = NewType("SnapshotId", str)
EvidenceId = NewType("EvidenceId", str)
HypothesisId = NewType("HypothesisId", str)
PhysicalAwnId = NewType("PhysicalAwnId", str)
PhysicalSpikeletId = NewType("PhysicalSpikeletId", str)
ProvisionalTrajectoryId = NewType("ProvisionalTrajectoryId", str)
AwnSpikeletAssociationId = NewType("AwnSpikeletAssociationId", str)
CompletenessAssessmentId = NewType("CompletenessAssessmentId", str)
RepresentativeDecisionId = NewType("RepresentativeDecisionId", str)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    text = _SLUG_RE.sub("-", str(value).strip().lower()).strip("-")
    if not text:
        raise ValueError("ID token must contain at least one alphanumeric character")
    return text


def _to_jsonable(value: Any) -> Any:
    """Convert supported immutable values into canonical JSON-compatible data."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _to_jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("provenance values must not contain NaN or infinity")
        return value
    raise TypeError(
        "provenance values must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


def _freeze_jsonlike(value: Any) -> Any:
    """Deep-copy JSON-like values into immutable containers."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_jsonlike(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_jsonlike(item) for item in value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("provenance values must not contain NaN or infinity")
        return value
    raise TypeError(
        "provenance values must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON-compatible data independently of mapping key order."""
    payload = json.dumps(
        _to_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _content_id(prefix: str, namespace: str, payload: Mapping[str, Any]) -> str:
    digest = canonical_json_sha256(
        {
            "namespace": namespace,
            "payload": payload,
        }
    )[:20]
    return f"{prefix}_{digest}"


def make_snapshot_id(provenance: Mapping[str, Any]) -> SnapshotId:
    """Create a deterministic snapshot ID from immutable run provenance."""
    if not provenance:
        raise ValueError("snapshot provenance must not be empty")
    return SnapshotId(
        _content_id("snap", "snapshot", dict(provenance))
    )


def make_evidence_id(
    *,
    snapshot_id: str,
    page_id: str,
    class_id: int,
    class_name: str,
    provider: str,
    source_tile_id: str,
    source_prediction_index: int,
    source_component_index: int = 0,
) -> EvidenceId:
    """Identify one immutable model observation inside an inference snapshot.

    source_prediction_index is a source-local model-output coordinate, not a
    post-processing list position. Downstream stages must use the returned ID
    rather than array indices as identity.
    """
    if int(source_prediction_index) < 0:
        raise ValueError("source_prediction_index must be >= 0")
    if int(source_component_index) < 0:
        raise ValueError("source_component_index must be >= 0")
    page_slug = _slug(page_id)
    class_slug = _slug(class_name)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "class_id": int(class_id),
        "class_name": str(class_name),
        "provider": str(provider),
        "source_tile_id": str(source_tile_id),
        "source_prediction_index": int(source_prediction_index),
    }
    if int(source_component_index) != 0:
        payload["source_component_index"] = int(source_component_index)
    digest = _content_id("id", "evidence", payload).split("_", 1)[1]
    return EvidenceId(f"evi_{class_slug}_{page_slug}_{digest}")


def make_hypothesis_id(
    *,
    snapshot_id: str,
    page_id: str,
    class_name: str,
    evidence_ids: Sequence[str],
) -> HypothesisId:
    """Identify an instance hypothesis by its evidence membership.

    Geometry and fusion strategy are deliberately excluded. The same evidence
    cluster remains the same hypothesis while geometry-reconstruction strategies
    are compared.
    """
    sources = sorted({str(value) for value in evidence_ids})
    if not sources:
        raise ValueError("instance hypothesis requires at least one evidence ID")
    page_slug = _slug(page_id)
    class_slug = _slug(class_name)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "class_name": str(class_name),
        "evidence_ids": sources,
    }
    digest = _content_id("id", "instance_hypothesis", payload).split("_", 1)[1]
    return HypothesisId(f"hyp_{class_slug}_{page_slug}_{digest}")


def _make_physical_entity_id(
    *,
    prefix: str,
    namespace: str,
    snapshot_id: str,
    page_id: str,
    seed_hypothesis_id: str,
) -> str:
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "seed_hypothesis_id": str(seed_hypothesis_id),
    }
    digest = _content_id("id", namespace, payload).split("_", 1)[1]
    return f"{prefix}_{page_slug}_{digest}"


def make_physical_awn_id(
    *,
    snapshot_id: str,
    page_id: str,
    seed_hypothesis_id: str,
) -> PhysicalAwnId:
    """Create stable PhysicalAwn identity from its reconciliation seed.

    Geometry and later reconstruction support are deliberately excluded so the
    physical entity keeps the same identity while its structure is repaired or
    extended in later Physical Reconstruction steps.
    """
    return PhysicalAwnId(
        _make_physical_entity_id(
            prefix="awn",
            namespace="physical_awn",
            snapshot_id=snapshot_id,
            page_id=page_id,
            seed_hypothesis_id=seed_hypothesis_id,
        )
    )


def make_physical_spikelet_id(
    *,
    snapshot_id: str,
    page_id: str,
    seed_hypothesis_id: str,
) -> PhysicalSpikeletId:
    """Create stable PhysicalSpikelet identity from its reconciliation seed."""
    return PhysicalSpikeletId(
        _make_physical_entity_id(
            prefix="spk",
            namespace="physical_spikelet",
            snapshot_id=snapshot_id,
            page_id=page_id,
            seed_hypothesis_id=seed_hypothesis_id,
        )
    )


def make_provisional_trajectory_id(
    *,
    snapshot_id: str,
    page_id: str,
    physical_awn_id: str,
    source_geometry_sha256: str,
    implementation: str,
) -> ProvisionalTrajectoryId:
    """Create a content ID for one provisional trajectory extraction."""
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "physical_awn_id": str(physical_awn_id),
        "source_geometry_sha256": str(source_geometry_sha256),
        "implementation": str(implementation),
    }
    digest = _content_id(
        "id",
        "provisional_trajectory",
        payload,
    ).split("_", 1)[1]
    return ProvisionalTrajectoryId(f"traj_{page_slug}_{digest}")


def make_awn_spikelet_association_id(
    *,
    snapshot_id: str,
    page_id: str,
    physical_awn_id: str,
    provisional_trajectory_id: str,
    active_spikelet_ids: Sequence[str],
    implementation: str,
) -> AwnSpikeletAssociationId:
    """Create a content ID for one provisional awn-spikelet association pass."""
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "physical_awn_id": str(physical_awn_id),
        "provisional_trajectory_id": str(provisional_trajectory_id),
        "active_spikelet_ids": sorted({str(value) for value in active_spikelet_ids}),
        "implementation": str(implementation),
    }
    digest = _content_id(
        "id",
        "awn_spikelet_association",
        payload,
    ).split("_", 1)[1]
    return AwnSpikeletAssociationId(f"assoc_{page_slug}_{digest}")


def make_completeness_assessment_id(
    *,
    snapshot_id: str,
    page_id: str,
    physical_awn_id: str,
    status: str,
    reasons: Sequence[str],
    supporting_evidence_ids: Sequence[str],
) -> CompletenessAssessmentId:
    """Create a content ID for one completeness judgement."""
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "physical_awn_id": str(physical_awn_id),
        "status": str(status),
        "reasons": sorted(str(value) for value in reasons),
        "supporting_evidence_ids": sorted(
            {str(value) for value in supporting_evidence_ids}
        ),
    }
    digest = _content_id("id", "completeness_assessment", payload).split("_", 1)[1]
    return CompletenessAssessmentId(f"cmp_{page_slug}_{digest}")


def make_representative_decision_id(
    *,
    snapshot_id: str,
    page_id: str,
    spikelet_id: str,
    candidate_awn_ids: Sequence[str],
    status: str,
    selected_awn_id: str | None,
) -> RepresentativeDecisionId:
    """Create a deterministic ID for one representative-selection outcome."""
    page_slug = _slug(page_id)
    payload = {
        "snapshot_id": str(snapshot_id),
        "page_id": str(page_id),
        "spikelet_id": str(spikelet_id),
        "candidate_awn_ids": sorted({str(value) for value in candidate_awn_ids}),
        "status": str(status),
        "selected_awn_id": (
            None if selected_awn_id is None else str(selected_awn_id)
        ),
    }
    digest = _content_id("id", "representative_decision", payload).split("_", 1)[1]
    return RepresentativeDecisionId(f"rep_{page_slug}_{digest}")


@dataclass(frozen=True, slots=True)
class OperationProvenance:
    """Auditable immutable record of one pipeline operation."""

    operation: str
    implementation: str
    input_ids: tuple[str, ...]
    output_id: str | None
    status: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        operation = str(self.operation).strip()
        implementation = str(self.implementation).strip()
        status = str(self.status).strip()
        if not operation:
            raise ValueError("operation must not be empty")
        if not implementation:
            raise ValueError("implementation must not be empty")
        if not status:
            raise ValueError("status must not be empty")

        input_ids = tuple(str(value) for value in self.input_ids)
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("provenance input_ids must be unique")

        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "implementation", implementation)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "input_ids", input_ids)
        object.__setattr__(
            self,
            "output_id",
            None if self.output_id is None else str(self.output_id),
        )
        object.__setattr__(
            self,
            "parameters",
            _freeze_jsonlike(dict(self.parameters)),
        )
        object.__setattr__(
            self,
            "evidence",
            _freeze_jsonlike(dict(self.evidence)),
        )

        canonical_json_sha256(self.payload())

    def payload(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "implementation": self.implementation,
            "input_ids": list(self.input_ids),
            "output_id": self.output_id,
            "status": self.status,
            "parameters": _to_jsonable(self.parameters),
            "evidence": _to_jsonable(self.evidence),
        }

    @property
    def provenance_id(self) -> str:
        return "prov_" + canonical_json_sha256(self.payload())[:20]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance_id": self.provenance_id,
            **self.payload(),
        }
