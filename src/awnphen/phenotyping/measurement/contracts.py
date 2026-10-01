"""Measurement result contracts used by physical-to-phenotype evaluation glue."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from awnphen.core.domain.physical_provenance import OperationProvenance, SnapshotId


class MeasurementStatus(str, Enum):
    MEASURED = "measured"
    REVIEW = "review"
    INVALID_CENTERLINE = "invalid_centerline"
    CALIBRATION_UNAVAILABLE = "calibration_unavailable"
    NO_REPRESENTATIVE = "no_representative"


@dataclass(frozen=True, slots=True)
class RepresentativeMeasurement:
    page_id: str
    snapshot_id: SnapshotId
    spikelet_id: str
    representative_decision_id: str
    physical_awn_id: str | None
    status: MeasurementStatus
    authoritative_centerline_status: str | None
    authoritative_centerline_path: tuple[tuple[float, float], ...]
    base_trim: Mapping[str, object]
    measurement_path: tuple[tuple[float, float], ...]
    raw_length_px: float | None
    measurement_length_px: float | None
    length_mm: float | None
    x_period_px: float | None
    y_period_px: float | None
    calibration_adequate: bool | None
    provenance: tuple[OperationProvenance, ...] = ()


@dataclass(frozen=True, slots=True)
class MeasurementPageResult:
    page_id: str
    snapshot_id: SnapshotId
    source_spikelet_ids: tuple[str, ...]
    measurements: tuple[RepresentativeMeasurement, ...]

    def __post_init__(self) -> None:
        source = tuple(sorted(str(value) for value in self.source_spikelet_ids))
        measured = tuple(sorted(item.spikelet_id for item in self.measurements))
        if source != measured:
            raise ValueError("measurement records must cover spikelets exactly")
        if len(source) != len(set(source)):
            raise ValueError("source spikelet IDs must be unique")
        for item in self.measurements:
            if item.page_id != self.page_id:
                raise ValueError("measurement page mismatch")
            if str(item.snapshot_id) != str(self.snapshot_id):
                raise ValueError("measurement snapshot mismatch")


__all__ = [
    "MeasurementStatus",
    "RepresentativeMeasurement",
    "MeasurementPageResult",
]
