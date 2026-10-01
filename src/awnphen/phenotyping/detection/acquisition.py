"""Phase 2A canonical DetectionEvidence acquisition core.

This module stops strictly before reconciliation. One raw model observation
becomes one immutable DetectionEvidence object; no merge, dedupe, confidence
pruning, reconstruction, or representative logic is allowed here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from shapely.geometry.base import BaseGeometry

from awnphen.core.domain.physical import DetectionEvidence, EvidenceProvider
from awnphen.core.domain.physical_provenance import (
    OperationProvenance,
    SnapshotId,
    canonical_json_sha256,
    make_snapshot_id,
)


EVIDENCE_SNAPSHOT_SCHEMA = "awnphen_detection_evidence_snapshot_v1"
EVIDENCE_ACQUISITION_IMPLEMENTATION = "awnphen_next_phase2a"

_CLASS_NAME_BY_ID = {
    0: "awn",
    1: "spikelet",
}

_REQUIRED_PROVIDER_PROVENANCE = (
    "implementation",
    "model_identity",
    "weights_sha256",
)


def _require_text(name: str, value: Any) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _freeze_jsonlike(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_jsonlike(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_jsonlike(item) for item in value)
    if value is None or isinstance(value, (str, int, bool, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("provenance must not contain NaN or infinity")
        return value
    raise TypeError(
        "provenance must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("provenance must not contain NaN or infinity")
        return value
    raise TypeError(
        "provenance must be JSON-compatible; "
        f"unsupported type: {type(value).__name__}"
    )


def _quad(
    name: str,
    value: Sequence[Any] | None,
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    result = tuple(float(item) for item in value)
    if len(result) != 4:
        raise ValueError(f"{name} must contain exactly four coordinates")
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{name} must contain only finite coordinates")
    return result


@dataclass(frozen=True, slots=True)
class RawDetectionObservation:
    """One provider-local observation already restored to page coordinates."""

    class_id: int
    class_name: str
    confidence: float
    geometry: BaseGeometry
    source_tile_id: str
    source_prediction_index: int
    source_component_index: int = 0
    tile_xyxy: tuple[float, float, float, float] | None = None
    box_xyxy: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        class_id = int(self.class_id)
        class_name = _require_text("class_name", self.class_name)
        expected_name = _CLASS_NAME_BY_ID.get(class_id)
        if expected_name is None:
            raise ValueError(f"unsupported class_id: {class_id}")
        if class_name != expected_name:
            raise ValueError(
                f"class_id={class_id} requires class_name={expected_name!r}, "
                f"got {class_name!r}"
            )

        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be finite and within [0, 1]")

        if not isinstance(self.geometry, BaseGeometry):
            raise TypeError("geometry must be a shapely BaseGeometry")
        if self.geometry.is_empty:
            raise ValueError("geometry must not be empty")

        source_tile_id = _require_text("source_tile_id", self.source_tile_id)
        source_prediction_index = int(self.source_prediction_index)
        if source_prediction_index < 0:
            raise ValueError("source_prediction_index must be >= 0")
        source_component_index = int(self.source_component_index)
        if source_component_index < 0:
            raise ValueError("source_component_index must be >= 0")

        object.__setattr__(self, "class_id", class_id)
        object.__setattr__(self, "class_name", class_name)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "source_tile_id", source_tile_id)
        object.__setattr__(
            self,
            "source_prediction_index",
            source_prediction_index,
        )
        object.__setattr__(
            self,
            "source_component_index",
            source_component_index,
        )
        object.__setattr__(self, "tile_xyxy", _quad("tile_xyxy", self.tile_xyxy))
        object.__setattr__(self, "box_xyxy", _quad("box_xyxy", self.box_xyxy))

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "geometry_wkb_hex": self.geometry.wkb_hex,
            "source_tile_id": self.source_tile_id,
            "source_prediction_index": self.source_prediction_index,
            "tile_xyxy": None if self.tile_xyxy is None else list(self.tile_xyxy),
            "box_xyxy": None if self.box_xyxy is None else list(self.box_xyxy),
        }
        if self.source_component_index != 0:
            payload["source_component_index"] = self.source_component_index
        return payload


@runtime_checkable
class DetectionObservationProvider(Protocol):
    """Primary/supplementary raw-observation provider contract."""

    @property
    def provider(self) -> EvidenceProvider:
        ...

    def provenance_payload(self) -> Mapping[str, Any]:
        ...

    def observe_page(
        self,
        *,
        page_id: str,
    ) -> tuple[RawDetectionObservation, ...]:
        ...


@dataclass(frozen=True, slots=True)
class EvidenceAcquisitionResult:
    """One page-level immutable evidence snapshot in memory."""

    page_id: str
    source_sha256: str
    snapshot_id: SnapshotId
    raw_observations_sha256: str
    providers: tuple[EvidenceProvider, ...]
    provider_provenance: Mapping[str, Mapping[str, Any]]
    evidence: tuple[DetectionEvidence, ...]

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        source_sha256 = _require_text("source_sha256", self.source_sha256)
        raw_hash = _require_text(
            "raw_observations_sha256",
            self.raw_observations_sha256,
        )
        providers = tuple(
            item
            if isinstance(item, EvidenceProvider)
            else EvidenceProvider(str(item))
            for item in self.providers
        )
        provider_provenance = _freeze_jsonlike(
            {
                str(key): dict(value)
                for key, value in self.provider_provenance.items()
            }
        )
        evidence = tuple(self.evidence)

        if len(providers) != len(set(providers)):
            raise ValueError("providers must be unique")

        for item in evidence:
            if item.page_id != page_id:
                raise ValueError("all evidence must belong to result page_id")
            if item.snapshot_id != self.snapshot_id:
                raise ValueError("all evidence must share result snapshot_id")
            if item.provider not in providers:
                raise ValueError("evidence provider missing from result providers")

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "source_sha256", source_sha256)
        object.__setattr__(self, "raw_observations_sha256", raw_hash)
        expected_provider_keys = {item.value for item in providers}
        if set(provider_provenance) != expected_provider_keys:
            raise ValueError(
                "provider_provenance keys must match result providers"
            )

        object.__setattr__(self, "providers", providers)
        object.__setattr__(
            self,
            "provider_provenance",
            provider_provenance,
        )
        object.__setattr__(self, "evidence", evidence)


def _provider_provenance(
    provider: DetectionObservationProvider,
    provider_kind: EvidenceProvider,
) -> dict[str, Any]:
    payload = _jsonable(provider.provenance_payload())
    missing = [
        key
        for key in _REQUIRED_PROVIDER_PROVENANCE
        if not str(payload.get(key, "")).strip()
    ]
    if missing:
        raise ValueError(
            "provider provenance missing required fields: "
            + ", ".join(missing)
        )
    if provider_kind is EvidenceProvider.SUPPLEMENTARY:
        supplementary_required = (
            "trigger_reason",
            "planned_tile_ids",
            "confidence",
        )
        missing = [
            key
            for key in supplementary_required
            if key not in payload
        ]
        if missing:
            raise ValueError(
                "supplementary provider provenance missing planning fields: "
                + ", ".join(missing)
            )
        planned_tiles = payload["planned_tile_ids"]
        if not isinstance(planned_tiles, list) or not planned_tiles:
            raise ValueError(
                "supplementary planned_tile_ids must be a non-empty list"
            )

    canonical_json_sha256(payload)
    return payload


def acquire_detection_evidence(
    *,
    page_id: str,
    source_sha256: str,
    providers: Sequence[DetectionObservationProvider],
) -> EvidenceAcquisitionResult:
    """Normalize raw page-coordinate observations into canonical evidence.

    This function is intentionally lossless with respect to observation count:
    every provider observation produces exactly one DetectionEvidence.
    """

    page_id = _require_text("page_id", page_id)
    source_sha256 = _require_text("source_sha256", source_sha256)
    providers = tuple(providers)
    if not providers:
        raise ValueError("at least one provider is required")

    provider_kinds = tuple(
        item.provider
        if isinstance(item.provider, EvidenceProvider)
        else EvidenceProvider(str(item.provider))
        for item in providers
    )
    if len(provider_kinds) != len(set(provider_kinds)):
        raise ValueError(
            "one acquisition snapshot may contain at most one provider "
            "implementation for each EvidenceProvider kind"
        )

    collected = []
    provider_records = []

    for provider, provider_kind in zip(providers, provider_kinds):
        provenance = _provider_provenance(provider, provider_kind)
        provider_records.append(
            {
                "provider": provider_kind.value,
                "provenance": provenance,
            }
        )
        for observation in provider.observe_page(page_id=page_id):
            collected.append((provider_kind, observation, provenance))

    identities = [
        (
            provider_kind.value,
            observation.source_tile_id,
            observation.source_prediction_index,
            observation.source_component_index,
        )
        for provider_kind, observation, _ in collected
    ]
    if len(identities) != len(set(identities)):
        raise ValueError(
            "duplicate provider/tile/source_prediction_index/component identity"
        )

    fingerprint_records = sorted(
        (
            {
                "provider": provider_kind.value,
                **observation.fingerprint_payload(),
            }
            for provider_kind, observation, _ in collected
        ),
        key=lambda item: (
            item["provider"],
            item["source_tile_id"],
            item["source_prediction_index"],
            item.get("source_component_index", 0),
        ),
    )
    raw_observations_sha256 = canonical_json_sha256(fingerprint_records)

    snapshot_id = make_snapshot_id(
        {
            "schema": EVIDENCE_SNAPSHOT_SCHEMA,
            "page_id": page_id,
            "source_sha256": source_sha256,
            "providers": sorted(
                provider_records,
                key=lambda item: item["provider"],
            ),
            "raw_observations_sha256": raw_observations_sha256,
        }
    )

    evidence = []
    for provider_kind, observation, provider_provenance in collected:
        draft = DetectionEvidence.create(
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_id=observation.class_id,
            class_name=observation.class_name,
            geometry=observation.geometry,
            confidence=observation.confidence,
            provider=provider_kind,
            source_tile_id=observation.source_tile_id,
            source_prediction_index=observation.source_prediction_index,
            source_component_index=observation.source_component_index,
        )

        provenance = OperationProvenance(
            operation="acquire_detection_evidence",
            implementation=EVIDENCE_ACQUISITION_IMPLEMENTATION,
            input_ids=(
                (
                    f"raw:{provider_kind.value}:"
                    f"{observation.source_tile_id}:"
                    f"{observation.source_prediction_index}:"
                    f"component_{observation.source_component_index:04d}"
                ),
            ),
            output_id=str(draft.evidence_id),
            status="observed",
            parameters={
                "provider": provider_kind.value,
                "provider_provenance": provider_provenance,
            },
            evidence={
                "page_id": page_id,
                "source_sha256": source_sha256,
                "coordinate_space": "page_px",
                "source_tile_id": observation.source_tile_id,
                "source_prediction_index": observation.source_prediction_index,
                "source_component_index": observation.source_component_index,
                "tile_xyxy": (
                    None
                    if observation.tile_xyxy is None
                    else list(observation.tile_xyxy)
                ),
                "box_xyxy_page": (
                    None
                    if observation.box_xyxy is None
                    else list(observation.box_xyxy)
                ),
            },
        )

        evidence.append(
            DetectionEvidence.create(
                snapshot_id=snapshot_id,
                page_id=page_id,
                class_id=observation.class_id,
                class_name=observation.class_name,
                geometry=observation.geometry,
                confidence=observation.confidence,
                provider=provider_kind,
                source_tile_id=observation.source_tile_id,
                source_prediction_index=observation.source_prediction_index,
                source_component_index=observation.source_component_index,
                provenance=(provenance,),
            )
        )

    evidence.sort(
        key=lambda item: (
            item.provider.value,
            item.source_tile_id,
            item.source_prediction_index,
            item.source_component_index,
        )
    )

    if len(evidence) != len(collected):
        raise AssertionError("evidence acquisition must preserve observation count")

    return EvidenceAcquisitionResult(
        page_id=page_id,
        source_sha256=source_sha256,
        snapshot_id=snapshot_id,
        raw_observations_sha256=raw_observations_sha256,
        providers=tuple(sorted(provider_kinds, key=lambda item: item.value)),
        provider_provenance={
            item["provider"]: item["provenance"]
            for item in provider_records
        },
        evidence=tuple(evidence),
    )


__all__ = [
    "EVIDENCE_ACQUISITION_IMPLEMENTATION",
    "EVIDENCE_SNAPSHOT_SCHEMA",
    "DetectionObservationProvider",
    "EvidenceAcquisitionResult",
    "RawDetectionObservation",
    "acquire_detection_evidence",
]
