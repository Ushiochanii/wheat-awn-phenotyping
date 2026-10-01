"""Core immutable contracts for the parallel awnphen_next pipeline.

Phase 1A intentionally defines identity and audit contracts only. Scientific
reconciliation, reconstruction, representative scoring, and measurement
algorithms belong to later phases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from shapely.geometry.base import BaseGeometry

from .physical_provenance import (
    CompletenessAssessmentId,
    EvidenceId,
    HypothesisId,
    OperationProvenance,
    PhysicalAwnId,
    PhysicalSpikeletId,
    ProvisionalTrajectoryId,
    RepresentativeDecisionId,
    SnapshotId,
    make_completeness_assessment_id,
    make_evidence_id,
    make_hypothesis_id,
    make_physical_awn_id,
    make_physical_spikelet_id,
    make_provisional_trajectory_id,
    make_representative_decision_id,
)


class EvidenceProvider(str, Enum):
    PRIMARY = "primary"
    SUPPLEMENTARY = "supplementary"


class HypothesisStatus(str, Enum):
    SINGLETON = "singleton"
    FUSED = "fused"
    AMBIGUOUS = "ambiguous"


class TrajectoryStatus(str, Enum):
    OK = "ok"
    FRAGMENTED = "fragmented"
    INVALID = "invalid"


class CompletenessStatus(str, Enum):
    COMPLETE = "complete"
    POSSIBLY_TRUNCATED = "possibly_truncated"
    FRAGMENTED = "fragmented"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class RepresentativeStatus(str, Enum):
    SELECTED = "selected"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


_CLASS_NAME_BY_ID = {
    0: "awn",
    1: "spikelet",
}


def _require_text(name: str, value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _require_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if not isinstance(geometry, BaseGeometry):
        raise TypeError("geometry must be a shapely BaseGeometry")
    if geometry.is_empty:
        raise ValueError("geometry must not be empty")
    return geometry


def _require_class_pair(class_id: int, class_name: str) -> tuple[int, str]:
    normalized_id = int(class_id)
    normalized_name = _require_text("class_name", class_name)
    expected = _CLASS_NAME_BY_ID.get(normalized_id)
    if expected is None:
        raise ValueError(f"unsupported class_id: {normalized_id}")
    if normalized_name != expected:
        raise ValueError(
            f"class_id={normalized_id} requires class_name={expected!r}, "
            f"got {normalized_name!r}"
        )
    return normalized_id, normalized_name


def _unique_sorted_ids(name: str, values) -> tuple[str, ...]:
    normalized = tuple(str(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicate IDs")
    return tuple(sorted(normalized))


def _normalize_physical_support(
    *,
    seed_hypothesis_id: str,
    source_hypothesis_ids,
    source_evidence_ids,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    seed = _require_text("seed_hypothesis_id", seed_hypothesis_id)
    hypotheses = _unique_sorted_ids(
        "source_hypothesis_ids",
        source_hypothesis_ids,
    )
    if not hypotheses:
        raise ValueError("physical entity requires at least one source hypothesis")
    if seed not in hypotheses:
        raise ValueError(
            "seed_hypothesis_id must be present in source_hypothesis_ids"
        )
    evidence = _unique_sorted_ids(
        "source_evidence_ids",
        source_evidence_ids,
    )
    if not evidence:
        raise ValueError("physical entity requires at least one source evidence ID")
    return seed, hypotheses, evidence


@dataclass(frozen=True, slots=True)
class DetectionEvidence:
    """One immutable model observation in page coordinates."""

    evidence_id: EvidenceId
    snapshot_id: SnapshotId
    page_id: str
    class_id: int
    class_name: str
    geometry: BaseGeometry
    confidence: float
    provider: EvidenceProvider
    source_tile_id: str
    source_prediction_index: int
    source_component_index: int = 0
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        class_id, class_name = _require_class_pair(self.class_id, self.class_name)
        geometry = _require_geometry(self.geometry)
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be finite and within [0, 1]")
        provider = (
            self.provider
            if isinstance(self.provider, EvidenceProvider)
            else EvidenceProvider(str(self.provider))
        )
        source_tile_id = _require_text("source_tile_id", self.source_tile_id)
        source_prediction_index = int(self.source_prediction_index)
        if source_prediction_index < 0:
            raise ValueError("source_prediction_index must be >= 0")
        source_component_index = int(self.source_component_index)
        if source_component_index < 0:
            raise ValueError("source_component_index must be >= 0")

        expected_id = make_evidence_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            class_id=class_id,
            class_name=class_name,
            provider=provider.value,
            source_tile_id=source_tile_id,
            source_prediction_index=source_prediction_index,
            source_component_index=source_component_index,
        )
        if str(self.evidence_id) != str(expected_id):
            raise ValueError(
                "evidence_id does not match immutable evidence identity"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "class_id", class_id)
        object.__setattr__(self, "class_name", class_name)
        object.__setattr__(self, "geometry", geometry)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "provider", provider)
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
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        class_id: int,
        class_name: str,
        geometry: BaseGeometry,
        confidence: float,
        provider: EvidenceProvider | str,
        source_tile_id: str,
        source_prediction_index: int,
        source_component_index: int = 0,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "DetectionEvidence":
        provider_value = (
            provider.value
            if isinstance(provider, EvidenceProvider)
            else EvidenceProvider(str(provider)).value
        )
        evidence_id = make_evidence_id(
            snapshot_id=str(snapshot_id),
            page_id=page_id,
            class_id=class_id,
            class_name=class_name,
            provider=provider_value,
            source_tile_id=source_tile_id,
            source_prediction_index=source_prediction_index,
            source_component_index=source_component_index,
        )
        return cls(
            evidence_id=evidence_id,
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_id=class_id,
            class_name=class_name,
            geometry=geometry,
            confidence=confidence,
            provider=EvidenceProvider(provider_value),
            source_tile_id=source_tile_id,
            source_prediction_index=source_prediction_index,
            source_component_index=source_component_index,
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class InstanceHypothesis:
    """A physical-instance hypothesis defined by immutable evidence membership.

    Identity is independent of the current reconstructed geometry so later
    reconciliation experiments can compare geometry strategies without changing
    the evidence-cluster identity.
    """

    hypothesis_id: HypothesisId
    snapshot_id: SnapshotId
    page_id: str
    class_id: int
    class_name: str
    evidence_ids: tuple[EvidenceId, ...]
    geometry: BaseGeometry
    status: HypothesisStatus
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        class_id, class_name = _require_class_pair(self.class_id, self.class_name)
        evidence_ids = _unique_sorted_ids("evidence_ids", self.evidence_ids)
        if not evidence_ids:
            raise ValueError("instance hypothesis requires at least one evidence ID")
        geometry = _require_geometry(self.geometry)
        status = (
            self.status
            if isinstance(self.status, HypothesisStatus)
            else HypothesisStatus(str(self.status))
        )

        expected_id = make_hypothesis_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            class_name=class_name,
            evidence_ids=evidence_ids,
        )
        if str(self.hypothesis_id) != str(expected_id):
            raise ValueError(
                "hypothesis_id does not match hypothesis evidence membership"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "class_id", class_id)
        object.__setattr__(self, "class_name", class_name)
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(EvidenceId(value) for value in evidence_ids),
        )
        object.__setattr__(self, "geometry", geometry)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        class_id: int,
        class_name: str,
        evidence_ids: tuple[EvidenceId, ...],
        geometry: BaseGeometry,
        status: HypothesisStatus | str,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "InstanceHypothesis":
        normalized_ids = _unique_sorted_ids("evidence_ids", evidence_ids)
        if not normalized_ids:
            raise ValueError("instance hypothesis requires at least one evidence ID")
        hypothesis_id = make_hypothesis_id(
            snapshot_id=str(snapshot_id),
            page_id=page_id,
            class_name=class_name,
            evidence_ids=normalized_ids,
        )
        return cls(
            hypothesis_id=hypothesis_id,
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_id=class_id,
            class_name=class_name,
            evidence_ids=tuple(EvidenceId(value) for value in normalized_ids),
            geometry=geometry,
            status=(
                status
                if isinstance(status, HypothesisStatus)
                else HypothesisStatus(str(status))
            ),
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class PhysicalAwn:
    """One physical awn entity seeded from reconciliation hypotheses."""

    physical_awn_id: PhysicalAwnId
    snapshot_id: SnapshotId
    page_id: str
    seed_hypothesis_id: HypothesisId
    source_hypothesis_ids: tuple[HypothesisId, ...]
    source_evidence_ids: tuple[EvidenceId, ...]
    geometry: BaseGeometry
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        seed, hypotheses, evidence = _normalize_physical_support(
            seed_hypothesis_id=str(self.seed_hypothesis_id),
            source_hypothesis_ids=self.source_hypothesis_ids,
            source_evidence_ids=self.source_evidence_ids,
        )
        geometry = _require_geometry(self.geometry)
        expected_id = make_physical_awn_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            seed_hypothesis_id=seed,
        )
        if str(self.physical_awn_id) != str(expected_id):
            raise ValueError(
                "physical_awn_id does not match physical awn seed identity"
            )
        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "seed_hypothesis_id", HypothesisId(seed))
        object.__setattr__(
            self,
            "source_hypothesis_ids",
            tuple(HypothesisId(value) for value in hypotheses),
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            tuple(EvidenceId(value) for value in evidence),
        )
        object.__setattr__(self, "geometry", geometry)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        seed_hypothesis_id: HypothesisId | str,
        source_hypothesis_ids: tuple[HypothesisId, ...],
        source_evidence_ids: tuple[EvidenceId, ...],
        geometry: BaseGeometry,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "PhysicalAwn":
        seed, hypotheses, evidence = _normalize_physical_support(
            seed_hypothesis_id=str(seed_hypothesis_id),
            source_hypothesis_ids=source_hypothesis_ids,
            source_evidence_ids=source_evidence_ids,
        )
        return cls(
            physical_awn_id=make_physical_awn_id(
                snapshot_id=str(snapshot_id),
                page_id=page_id,
                seed_hypothesis_id=seed,
            ),
            snapshot_id=snapshot_id,
            page_id=page_id,
            seed_hypothesis_id=HypothesisId(seed),
            source_hypothesis_ids=tuple(
                HypothesisId(value) for value in hypotheses
            ),
            source_evidence_ids=tuple(
                EvidenceId(value) for value in evidence
            ),
            geometry=geometry,
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class PhysicalSpikelet:
    """One physical spikelet entity seeded from reconciliation hypotheses."""

    physical_spikelet_id: PhysicalSpikeletId
    snapshot_id: SnapshotId
    page_id: str
    seed_hypothesis_id: HypothesisId
    source_hypothesis_ids: tuple[HypothesisId, ...]
    source_evidence_ids: tuple[EvidenceId, ...]
    geometry: BaseGeometry
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        seed, hypotheses, evidence = _normalize_physical_support(
            seed_hypothesis_id=str(self.seed_hypothesis_id),
            source_hypothesis_ids=self.source_hypothesis_ids,
            source_evidence_ids=self.source_evidence_ids,
        )
        geometry = _require_geometry(self.geometry)
        expected_id = make_physical_spikelet_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            seed_hypothesis_id=seed,
        )
        if str(self.physical_spikelet_id) != str(expected_id):
            raise ValueError(
                "physical_spikelet_id does not match physical spikelet seed identity"
            )
        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "seed_hypothesis_id", HypothesisId(seed))
        object.__setattr__(
            self,
            "source_hypothesis_ids",
            tuple(HypothesisId(value) for value in hypotheses),
        )
        object.__setattr__(
            self,
            "source_evidence_ids",
            tuple(EvidenceId(value) for value in evidence),
        )
        object.__setattr__(self, "geometry", geometry)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        seed_hypothesis_id: HypothesisId | str,
        source_hypothesis_ids: tuple[HypothesisId, ...],
        source_evidence_ids: tuple[EvidenceId, ...],
        geometry: BaseGeometry,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "PhysicalSpikelet":
        seed, hypotheses, evidence = _normalize_physical_support(
            seed_hypothesis_id=str(seed_hypothesis_id),
            source_hypothesis_ids=source_hypothesis_ids,
            source_evidence_ids=source_evidence_ids,
        )
        return cls(
            physical_spikelet_id=make_physical_spikelet_id(
                snapshot_id=str(snapshot_id),
                page_id=page_id,
                seed_hypothesis_id=seed,
            ),
            snapshot_id=snapshot_id,
            page_id=page_id,
            seed_hypothesis_id=HypothesisId(seed),
            source_hypothesis_ids=tuple(
                HypothesisId(value) for value in hypotheses
            ),
            source_evidence_ids=tuple(
                EvidenceId(value) for value in evidence
            ),
            geometry=geometry,
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class ProvisionalTrajectory:
    """Unrooted trajectory used only for physical-structure reasoning."""

    trajectory_id: ProvisionalTrajectoryId
    snapshot_id: SnapshotId
    page_id: str
    physical_awn_id: PhysicalAwnId
    status: TrajectoryStatus
    path: tuple[tuple[float, float], ...]
    length_px: float
    source_geometry_sha256: str
    vector_component_count: int
    implementation: str
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        physical_awn_id = _require_text(
            "physical_awn_id",
            str(self.physical_awn_id),
        )
        source_geometry_sha256 = _require_text(
            "source_geometry_sha256",
            self.source_geometry_sha256,
        )
        implementation = _require_text(
            "implementation",
            self.implementation,
        )
        status = (
            self.status
            if isinstance(self.status, TrajectoryStatus)
            else TrajectoryStatus(str(self.status))
        )
        path = tuple(
            (float(point[0]), float(point[1]))
            for point in self.path
        )
        if any(
            not math.isfinite(value)
            for point in path
            for value in point
        ):
            raise ValueError("trajectory path coordinates must be finite")
        length_px = float(self.length_px)
        if not math.isfinite(length_px) or length_px < 0.0:
            raise ValueError("trajectory length_px must be finite and >= 0")
        vector_component_count = int(self.vector_component_count)
        if vector_component_count < 1:
            raise ValueError("vector_component_count must be >= 1")

        if status is TrajectoryStatus.INVALID:
            if path or length_px != 0.0:
                raise ValueError(
                    "invalid trajectory must have empty path and zero length"
                )
        elif len(path) < 2 or length_px <= 0.0:
            raise ValueError(
                "valid/fragmented trajectory requires a nonzero path"
            )

        expected_id = make_provisional_trajectory_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            physical_awn_id=physical_awn_id,
            source_geometry_sha256=source_geometry_sha256,
            implementation=implementation,
        )
        if str(self.trajectory_id) != str(expected_id):
            raise ValueError(
                "trajectory_id does not match provisional trajectory identity"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(
            self,
            "physical_awn_id",
            PhysicalAwnId(physical_awn_id),
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "length_px", length_px)
        object.__setattr__(
            self,
            "source_geometry_sha256",
            source_geometry_sha256,
        )
        object.__setattr__(
            self,
            "vector_component_count",
            vector_component_count,
        )
        object.__setattr__(self, "implementation", implementation)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @property
    def endpoint_candidates(
        self,
    ) -> tuple[tuple[float, float], ...]:
        if len(self.path) < 2:
            return ()
        return (self.path[0], self.path[-1])

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        physical_awn_id: PhysicalAwnId | str,
        status: TrajectoryStatus | str,
        path: tuple[tuple[float, float], ...],
        length_px: float,
        source_geometry_sha256: str,
        vector_component_count: int,
        implementation: str,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "ProvisionalTrajectory":
        trajectory_id = make_provisional_trajectory_id(
            snapshot_id=str(snapshot_id),
            page_id=page_id,
            physical_awn_id=str(physical_awn_id),
            source_geometry_sha256=source_geometry_sha256,
            implementation=implementation,
        )
        return cls(
            trajectory_id=trajectory_id,
            snapshot_id=snapshot_id,
            page_id=page_id,
            physical_awn_id=PhysicalAwnId(str(physical_awn_id)),
            status=(
                status
                if isinstance(status, TrajectoryStatus)
                else TrajectoryStatus(str(status))
            ),
            path=path,
            length_px=length_px,
            source_geometry_sha256=source_geometry_sha256,
            vector_component_count=vector_component_count,
            implementation=implementation,
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class CompletenessAssessment:
    """Explicit completeness judgement for one reconstructed PhysicalAwn."""

    assessment_id: CompletenessAssessmentId
    snapshot_id: SnapshotId
    page_id: str
    physical_awn_id: str
    status: CompletenessStatus
    reasons: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[EvidenceId, ...] = ()
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        physical_awn_id = _require_text("physical_awn_id", self.physical_awn_id)
        status = (
            self.status
            if isinstance(self.status, CompletenessStatus)
            else CompletenessStatus(str(self.status))
        )
        reasons = tuple(
            sorted(
                {
                    _require_text("completeness reason", value)
                    for value in self.reasons
                }
            )
        )
        supporting = _unique_sorted_ids(
            "supporting_evidence_ids",
            self.supporting_evidence_ids,
        )

        expected_id = make_completeness_assessment_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            physical_awn_id=physical_awn_id,
            status=status.value,
            reasons=reasons,
            supporting_evidence_ids=supporting,
        )
        if str(self.assessment_id) != str(expected_id):
            raise ValueError(
                "assessment_id does not match completeness judgement content"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "physical_awn_id", physical_awn_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self,
            "supporting_evidence_ids",
            tuple(EvidenceId(value) for value in supporting),
        )
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        physical_awn_id: str,
        status: CompletenessStatus | str,
        reasons: tuple[str, ...] = (),
        supporting_evidence_ids: tuple[EvidenceId, ...] = (),
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "CompletenessAssessment":
        normalized_status = (
            status
            if isinstance(status, CompletenessStatus)
            else CompletenessStatus(str(status))
        )
        normalized_reasons = tuple(
            sorted(
                {
                    _require_text("completeness reason", value)
                    for value in reasons
                }
            )
        )
        supporting = _unique_sorted_ids(
            "supporting_evidence_ids",
            supporting_evidence_ids,
        )
        assessment_id = make_completeness_assessment_id(
            snapshot_id=str(snapshot_id),
            page_id=page_id,
            physical_awn_id=physical_awn_id,
            status=normalized_status.value,
            reasons=normalized_reasons,
            supporting_evidence_ids=supporting,
        )
        return cls(
            assessment_id=assessment_id,
            snapshot_id=snapshot_id,
            page_id=page_id,
            physical_awn_id=physical_awn_id,
            status=normalized_status,
            reasons=normalized_reasons,
            supporting_evidence_ids=tuple(
                EvidenceId(value) for value in supporting
            ),
            provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class RepresentativeDecision:
    """Selection outcome for one spikelet after physical geometry is frozen."""

    decision_id: RepresentativeDecisionId
    snapshot_id: SnapshotId
    page_id: str
    spikelet_id: str
    candidate_awn_ids: tuple[str, ...]
    status: RepresentativeStatus
    selected_awn_id: str | None
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = _require_text("page_id", self.page_id)
        spikelet_id = _require_text("spikelet_id", self.spikelet_id)
        candidates = _unique_sorted_ids(
            "candidate_awn_ids",
            self.candidate_awn_ids,
        )
        status = (
            self.status
            if isinstance(self.status, RepresentativeStatus)
            else RepresentativeStatus(str(self.status))
        )
        selected = (
            None
            if self.selected_awn_id is None
            else _require_text("selected_awn_id", self.selected_awn_id)
        )

        if status is RepresentativeStatus.SELECTED:
            if selected is None:
                raise ValueError("selected decision requires selected_awn_id")
            if selected not in candidates:
                raise ValueError(
                    "selected_awn_id must be present in candidate_awn_ids"
                )
        elif selected is not None:
            raise ValueError(
                "ambiguous/none representative decisions cannot select an awn"
            )

        expected_id = make_representative_decision_id(
            snapshot_id=str(self.snapshot_id),
            page_id=page_id,
            spikelet_id=spikelet_id,
            candidate_awn_ids=candidates,
            status=status.value,
            selected_awn_id=selected,
        )
        if str(self.decision_id) != str(expected_id):
            raise ValueError(
                "decision_id does not match representative decision content"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(self, "spikelet_id", spikelet_id)
        object.__setattr__(self, "candidate_awn_ids", candidates)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "selected_awn_id", selected)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotId,
        page_id: str,
        spikelet_id: str,
        candidate_awn_ids: tuple[str, ...],
        status: RepresentativeStatus | str,
        selected_awn_id: str | None = None,
        provenance: tuple[OperationProvenance, ...] = (),
    ) -> "RepresentativeDecision":
        normalized_status = (
            status
            if isinstance(status, RepresentativeStatus)
            else RepresentativeStatus(str(status))
        )
        candidates = _unique_sorted_ids(
            "candidate_awn_ids",
            candidate_awn_ids,
        )
        decision_id = make_representative_decision_id(
            snapshot_id=str(snapshot_id),
            page_id=page_id,
            spikelet_id=spikelet_id,
            candidate_awn_ids=candidates,
            status=normalized_status.value,
            selected_awn_id=selected_awn_id,
        )
        return cls(
            decision_id=decision_id,
            snapshot_id=snapshot_id,
            page_id=page_id,
            spikelet_id=spikelet_id,
            candidate_awn_ids=candidates,
            status=normalized_status,
            selected_awn_id=selected_awn_id,
            provenance=provenance,
        )
