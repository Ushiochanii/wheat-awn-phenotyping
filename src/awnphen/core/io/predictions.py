"""Adapters from historical prediction JSON records to domain detections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from awnphen.core.domain.entities import Detection
from awnphen.core.domain.ids import SnapshotId, make_detection_id
from awnphen.core.domain.provenance import (
    InferenceProvenance,
    inference_provenance_from_payload,
)
from awnphen.core.geometry.instances import geometry_from_rings

DEFAULT_CLASS_NAMES = {
    0: "awn",
    1: "spikelet",
}


@dataclass(frozen=True)
class PredictionSnapshot:
    provenance: InferenceProvenance
    detections: tuple[Detection, ...]

    @property
    def snapshot_id(self) -> SnapshotId:
        return self.provenance.snapshot_id

    @property
    def page_id(self) -> str:
        return self.provenance.page_id


def adapt_prediction_records(
    records: Sequence[Mapping[str, Any]],
    *,
    snapshot_id: SnapshotId,
    page_id: str,
    class_names: Mapping[int, str] = DEFAULT_CLASS_NAMES,
) -> tuple[Detection, ...]:
    """Adapt final prediction records while preserving historical skip semantics.

    Empty/degenerate geometries are skipped exactly like legacy load_items(). The stable
    detection ID uses the original source record index, so skipping an earlier invalid
    record never renumbers later detections.
    """
    detections: list[Detection] = []

    for source_record_index, record in enumerate(records):
        geometry = geometry_from_rings(record["page_rings"])
        if geometry.is_empty:
            continue

        class_id = int(record["class_id"])
        try:
            class_name = str(class_names[class_id])
        except KeyError as exc:
            raise ValueError(
                f"no class name configured for class_id={class_id}"
            ) from exc

        detection_id = make_detection_id(
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_name=class_name,
            source_record_index=source_record_index,
        )

        detections.append(
            Detection(
                detection_id=detection_id,
                snapshot_id=snapshot_id,
                page_id=str(page_id),
                source_record_index=source_record_index,
                class_id=class_id,
                class_name=class_name,
                confidence=float(record.get("confidence", 0.0)),
                geometry=geometry,
                source_prediction_indices=tuple(
                    int(value)
                    for value in record.get(
                        "source_prediction_indices",
                        (),
                    )
                ),
                source_tiles=tuple(
                    int(value)
                    for value in record.get(
                        "source_tiles",
                        (),
                    )
                ),
                legacy_record=dict(record),
            )
        )

    return tuple(detections)


def adapt_prediction_payload(
    payload: Mapping[str, Any],
    *,
    class_names: Mapping[int, str] = DEFAULT_CLASS_NAMES,
) -> PredictionSnapshot:
    """Adapt a historical inference payload into a stable-identity snapshot."""
    provenance = inference_provenance_from_payload(payload)
    detections = adapt_prediction_records(
        payload["predictions"],
        snapshot_id=provenance.snapshot_id,
        page_id=provenance.page_id,
        class_names=class_names,
    )
    return PredictionSnapshot(
        provenance=provenance,
        detections=detections,
    )
