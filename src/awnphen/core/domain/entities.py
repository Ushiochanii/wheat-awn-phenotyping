"""Core domain entities introduced incrementally during the refactor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from shapely.geometry.base import BaseGeometry

from .ids import (
    DetectionId,
    PhysicalEntityId,
    SnapshotId,
    make_physical_awn_id,
    make_physical_spikelet_id,
)
from .provenance import OperationProvenance


@dataclass(frozen=True)
class Detection:
    """One immutable segmentation detection inside a specific inference snapshot."""

    detection_id: DetectionId
    snapshot_id: SnapshotId
    page_id: str
    source_record_index: int
    class_id: int
    class_name: str
    confidence: float
    geometry: BaseGeometry
    source_prediction_indices: tuple[int, ...]
    source_tiles: tuple[int, ...]
    legacy_record: Mapping[str, Any]

    def to_legacy_item(self) -> dict[str, Any]:
        """Reconstruct the historical load_items() shape without adding new fields."""
        return {
            **dict(self.legacy_record),
            "record_index": self.source_record_index,
            "geometry": self.geometry,
        }


@dataclass(frozen=True)
class PhysicalSpikelet:
    """Accepted physical spikelet within one analysis snapshot."""

    entity_id: PhysicalEntityId
    snapshot_id: SnapshotId
    page_id: str
    source_detection_ids: tuple[DetectionId, ...]
    geometry: BaseGeometry
    source_confidences: tuple[float, ...]
    provenance: tuple[OperationProvenance, ...]



@dataclass(frozen=True)
class SemanticAssignment:
    """Automatic semantic suggestion for one already-measured physical spikelet."""

    spikelet_id: PhysicalEntityId
    page_id: str
    column: int | None
    repeat: int | None
    slot_suggestion: str | None
    biological_role: str | None
    possible_biological_roles: tuple[str, ...]
    biological_role_status: str
    line_no: int | None
    strain_no: int | None
    accession: str | None
    workbook_key: str | None
    source: str = "auto"
    semantic_status: str = "resolved_exact"
    review_required: bool = False
    layout_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageSemanticAssignment:
    """Semantic interpretation of one physical PageMeasurement snapshot.

    This result intentionally contains no geometry, centerlines, or physical
    lengths. Those remain in PageMeasurement and are joined only for review or
    downstream export.
    """

    page_id: str
    snapshot_id: SnapshotId
    assignments: tuple[SemanticAssignment, ...]
    assignment_provenance: Mapping[str, Any] = field(default_factory=dict)
    page_qc: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        spikelet_ids: set[PhysicalEntityId] = set()
        for assignment in self.assignments:
            if assignment.page_id != self.page_id:
                raise ValueError(
                    "PageSemanticAssignment rows must all belong to page_id"
                )
            if assignment.spikelet_id in spikelet_ids:
                raise ValueError(
                    "PageSemanticAssignment contains duplicate spikelet assignments"
                )
            spikelet_ids.add(assignment.spikelet_id)

    @property
    def by_spikelet_id(self) -> Mapping[
        PhysicalEntityId,
        SemanticAssignment,
    ]:
        return {
            assignment.spikelet_id: assignment
            for assignment in self.assignments
        }


SEMANTIC_OVERRIDE_FIELDS = frozenset(
    {
        "column",
        "repeat",
        "biological_role",
        "line_no",
        "strain_no",
        "accession",
    }
)


@dataclass(frozen=True)
class AssignmentOverride:
    """One explicit manual semantic edit bound to a physical spikelet snapshot."""

    spikelet_id: PhysicalEntityId
    page_id: str
    snapshot_id: SnapshotId
    values: Mapping[str, Any]
    reason: str = ""
    source: str = "manual"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = dict(self.values)
        if not values:
            raise ValueError(
                "AssignmentOverride values must not be empty"
            )
        unknown = set(values) - SEMANTIC_OVERRIDE_FIELDS
        if unknown:
            raise ValueError(
                "AssignmentOverride contains unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        if (
            "accession" in values
            and (
                "line_no" in values
                or "strain_no" in values
            )
        ):
            raise ValueError(
                "Override accession directly or line_no/strain_no, not both"
            )


@dataclass(frozen=True)
class AssignmentOverrideSet:
    """Serializable override collection for one page and one analysis snapshot."""

    page_id: str
    snapshot_id: SnapshotId
    overrides: tuple[AssignmentOverride, ...]
    schema_version: str = "assignment_override_v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        seen: set[PhysicalEntityId] = set()
        for override in self.overrides:
            if override.page_id != self.page_id:
                raise ValueError(
                    "AssignmentOverrideSet contains an override from another page"
                )
            if override.snapshot_id != self.snapshot_id:
                raise ValueError(
                    "AssignmentOverrideSet contains an override from another snapshot"
                )
            if override.spikelet_id in seen:
                raise ValueError(
                    "AssignmentOverrideSet contains duplicate spikelet overrides"
                )
            seen.add(override.spikelet_id)


@dataclass(frozen=True)
class PageEffectiveSemanticAssignment:
    """Auto semantic assignments plus replayed manual overrides."""

    page_id: str
    snapshot_id: SnapshotId
    auto_page: PageSemanticAssignment
    effective_assignments: tuple[SemanticAssignment, ...]
    overrides: tuple[AssignmentOverride, ...] = ()
    override_provenance: Mapping[str, Any] = field(default_factory=dict)
    page_qc: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.auto_page.page_id != self.page_id:
            raise ValueError(
                "PageEffectiveSemanticAssignment auto page_id mismatch"
            )
        if self.auto_page.snapshot_id != self.snapshot_id:
            raise ValueError(
                "PageEffectiveSemanticAssignment auto snapshot_id mismatch"
            )

        auto_ids = {
            assignment.spikelet_id
            for assignment in self.auto_page.assignments
        }
        effective_ids: set[PhysicalEntityId] = set()
        for assignment in self.effective_assignments:
            if assignment.page_id != self.page_id:
                raise ValueError(
                    "Effective semantic rows must all belong to page_id"
                )
            if assignment.spikelet_id in effective_ids:
                raise ValueError(
                    "Effective semantic rows contain duplicate spikelet IDs"
                )
            effective_ids.add(assignment.spikelet_id)

        if effective_ids != auto_ids:
            raise ValueError(
                "Effective semantic rows must cover exactly the auto semantic rows"
            )

    @property
    def auto_by_spikelet_id(self) -> Mapping[
        PhysicalEntityId,
        SemanticAssignment,
    ]:
        return self.auto_page.by_spikelet_id

    @property
    def effective_by_spikelet_id(self) -> Mapping[
        PhysicalEntityId,
        SemanticAssignment,
    ]:
        return {
            assignment.spikelet_id: assignment
            for assignment in self.effective_assignments
        }


@dataclass(frozen=True)
class AwnMeasurement:
    """Physical measurement of one already-accepted PhysicalAwn.

    A missing length is represented by None plus an explicit status. This is
    deliberately different from a measured physical length of 0.0 mm.
    """

    awn_id: PhysicalEntityId
    spikelet_id: PhysicalEntityId | None
    centerline_status: str
    centerline_path: tuple[tuple[float, float], ...]
    raw_length_px: float | None
    length_mm: float | None
    status: str
    provenance: tuple[OperationProvenance, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    measurement_centerline_path: tuple[tuple[float, float], ...] = ()
    measurement_length_px: float | None = None


@dataclass(frozen=True)
class PhysicalAwn:
    """Accepted/assembled physical awn within one analysis snapshot."""

    entity_id: PhysicalEntityId
    snapshot_id: SnapshotId
    page_id: str
    source_detection_ids: tuple[DetectionId, ...]
    geometry: BaseGeometry
    source_confidences: tuple[float, ...]
    provenance: tuple[OperationProvenance, ...]


@dataclass(frozen=True)
class AwnSpikeletAssociation:
    """Physical parent relationship between one awn and one spikelet."""

    awn_id: PhysicalEntityId
    spikelet_id: PhysicalEntityId | None
    status: str
    association_centerline_status: str
    association_centerline_path: tuple[tuple[float, float], ...]
    association_centerline_length_px: float
    base_endpoint_index: int | None
    base: tuple[float, float] | None
    tip: tuple[float, float] | None
    base_distance_px: float | None
    second_parent_distance_px: float | None
    parent_margin_px: float | None
    provenance: tuple[OperationProvenance, ...] = ()

    @property
    def accepted_candidate(self) -> bool:
        return self.status == "accepted"

    @property
    def included_candidate(self) -> bool:
        return self.status in {"accepted", "review_near_base"}


@dataclass(frozen=True)
class PageMeasurement:
    """Self-contained physical result for one page and one analysis snapshot.

    Semantic fields such as accession, repeat, and bottom/middle/top intentionally
    do not live here.
    """

    page_id: str
    snapshot_id: SnapshotId
    spikelets: tuple[PhysicalSpikelet, ...]
    awns: tuple[PhysicalAwn, ...]
    awn_measurements: tuple[AwnMeasurement, ...]
    awn_spikelet_associations: tuple[AwnSpikeletAssociation, ...] = ()
    representative_awn_by_spikelet: Mapping[
        PhysicalEntityId,
        PhysicalEntityId | None,
    ] = field(default_factory=dict)
    analysis_provenance: Mapping[str, Any] = field(default_factory=dict)
    calibration: Mapping[str, Any] = field(default_factory=dict)
    page_qc: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        spikelet_ids = {spikelet.entity_id for spikelet in self.spikelets}
        awn_ids = {awn.entity_id for awn in self.awns}

        for entity in (*self.spikelets, *self.awns):
            if entity.page_id != self.page_id:
                raise ValueError(
                    "PageMeasurement entities must all belong to page_id"
                )
            if entity.snapshot_id != self.snapshot_id:
                raise ValueError(
                    "PageMeasurement entities must all belong to snapshot_id"
                )

        associated_awn_ids: set[PhysicalEntityId] = set()
        for association in self.awn_spikelet_associations:
            if association.awn_id not in awn_ids:
                raise ValueError(
                    "AwnSpikeletAssociation references an awn outside this page"
                )
            if association.awn_id in associated_awn_ids:
                raise ValueError(
                    "PageMeasurement contains duplicate awn-spikelet associations"
                )
            associated_awn_ids.add(association.awn_id)
            if (
                association.spikelet_id is not None
                and association.spikelet_id not in spikelet_ids
            ):
                raise ValueError(
                    "AwnSpikeletAssociation references a spikelet outside this page"
                )

        measured_awn_ids: set[PhysicalEntityId] = set()
        measurement_by_awn: dict[PhysicalEntityId, AwnMeasurement] = {}
        for measurement in self.awn_measurements:
            if measurement.awn_id not in awn_ids:
                raise ValueError(
                    "AwnMeasurement references an awn outside this page"
                )
            if measurement.awn_id in measured_awn_ids:
                raise ValueError(
                    "PageMeasurement contains duplicate awn measurements"
                )
            measured_awn_ids.add(measurement.awn_id)
            measurement_by_awn[measurement.awn_id] = measurement
            if (
                measurement.spikelet_id is not None
                and measurement.spikelet_id not in spikelet_ids
            ):
                raise ValueError(
                    "AwnMeasurement references a spikelet outside this page"
                )

        for spikelet_id, awn_id in self.representative_awn_by_spikelet.items():
            if spikelet_id not in spikelet_ids:
                raise ValueError(
                    "Representative mapping references an unknown spikelet"
                )
            if awn_id is None:
                continue
            if awn_id not in awn_ids:
                raise ValueError(
                    "Representative mapping references an unknown awn"
                )
            if awn_id not in measured_awn_ids:
                raise ValueError(
                    "Representative awn must have an AwnMeasurement"
                )
            if measurement_by_awn[awn_id].spikelet_id != spikelet_id:
                raise ValueError(
                    "Representative awn measurement must reference the same spikelet"
                )


def seed_spikelet_from_detection(
    detection: Detection,
    *,
    implementation: str = "domain_seed_v1",
    evidence: Mapping[str, Any] | None = None,
) -> PhysicalSpikelet:
    """Promote one explicitly accepted spikelet detection into a physical entity."""
    if detection.class_name != "spikelet":
        raise ValueError(
            "seed_spikelet_from_detection requires class_name='spikelet'"
        )

    entity_id = make_physical_spikelet_id(
        snapshot_id=detection.snapshot_id,
        page_id=detection.page_id,
        source_detection_ids=[detection.detection_id],
    )
    provenance = OperationProvenance(
        operation="seed_physical_spikelet",
        implementation=implementation,
        input_ids=(str(detection.detection_id),),
        output_id=str(entity_id),
        status="accepted",
        evidence=dict(evidence or {}),
    )
    return PhysicalSpikelet(
        entity_id=entity_id,
        snapshot_id=detection.snapshot_id,
        page_id=detection.page_id,
        source_detection_ids=(detection.detection_id,),
        geometry=detection.geometry,
        source_confidences=(detection.confidence,),
        provenance=(provenance,),
    )


def seed_awn_from_detection(
    detection: Detection,
    *,
    implementation: str = "domain_seed_v1",
    evidence: Mapping[str, Any] | None = None,
) -> PhysicalAwn:
    """Promote one explicitly accepted awn detection into a physical entity."""
    if detection.class_name != "awn":
        raise ValueError(
            "seed_awn_from_detection requires class_name='awn'"
        )

    entity_id = make_physical_awn_id(
        snapshot_id=detection.snapshot_id,
        page_id=detection.page_id,
        source_detection_ids=[detection.detection_id],
    )
    provenance = OperationProvenance(
        operation="seed_physical_awn",
        implementation=implementation,
        input_ids=(str(detection.detection_id),),
        output_id=str(entity_id),
        status="accepted",
        evidence=dict(evidence or {}),
    )
    return PhysicalAwn(
        entity_id=entity_id,
        snapshot_id=detection.snapshot_id,
        page_id=detection.page_id,
        source_detection_ids=(detection.detection_id,),
        geometry=detection.geometry,
        source_confidences=(detection.confidence,),
        provenance=(provenance,),
    )
