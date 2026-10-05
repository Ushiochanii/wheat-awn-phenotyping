"""Layout-free physical cleanup for PhysicalSpikelet seeds.

The stage preserves every seeded PhysicalSpikelet as provenance, but marks
obvious tiny-fragment false positives as rejected from downstream physical
association. Biological identity and fixed page layout are never used.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

import math
import numpy as np
from shapely.geometry import box

from awnphen.core.domain.physical import DetectionEvidence, PhysicalSpikelet
from awnphen.core.domain.physical_provenance import (
    OperationProvenance,
    PhysicalSpikeletId,
    SnapshotId,
    canonical_json_sha256,
)

# ---- spikelet candidate diagnostics ---------------------------------------
MAX_CONFIDENCE = 0.50
MAX_AREA_RATIO_TO_OTHER_MEDIAN = 0.20
EXTENDED_MAX_AREA_RATIO_TO_OTHER_MEDIAN = 0.30
EXTENDED_MIN_NORMALIZED_NEAREST_DISTANCE = 3.0
DEFAULT_NEIGHBOR_COUNT = 3
MIN_NEIGHBORS_FOR_RELATIVE_AREA = 2


def _centroid_xy(item):
    centroid = item["geometry"].centroid
    return float(centroid.x), float(centroid.y)


def spikelet_shape_metrics(item):
    """Return scale-independent shape descriptors.

    rotated_aspect and solidity intentionally match the historical runner.
    Extent and compactness are audit-only additions and have no delete threshold.
    """
    geom = item["geometry"]
    rect = geom.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)[:4]
    if len(coords) < 4:
        rotated_aspect = float("inf")
    else:
        edges = [
            float(
                np.hypot(
                    coords[(i + 1) % 4][0] - coords[i][0],
                    coords[(i + 1) % 4][1] - coords[i][1],
                )
            )
            for i in range(4)
        ]
        rotated_aspect = max(edges) / max(1e-9, min(edges))

    solidity = float(geom.area / max(1e-9, geom.convex_hull.area))
    min_x, min_y, max_x, max_y = geom.bounds
    bbox_area = max(1e-9, float(max_x - min_x) * float(max_y - min_y))
    extent = float(geom.area / bbox_area)
    perimeter = float(geom.length)
    compactness = float(
        4.0 * math.pi * float(geom.area)
        / max(1e-9, perimeter * perimeter)
    )
    return {
        "rotated_aspect": float(rotated_aspect),
        "solidity": solidity,
        "extent": extent,
        "compactness": compactness,
    }


def evaluate_layout_free_spikelet_candidates(
    spikelets,
    *,
    neighbor_count: int = DEFAULT_NEIGHBOR_COUNT,
):
    """Evaluate candidates without fixed page layout or semantic identity.

    The layout-free tiny-fragment evidence is:
    area / neighbour-median-area <= 0.20.

    Candidate confidence is recorded but is not a gate. Human audit across the
    characterization corpus showed high-confidence tiny fragments can still be
    false spikelets. Reference neighbours remain restricted to confidence >= 0.50
    so clusters of low-confidence false fragments cannot normalize one another.
    Fewer than two
    trusted neighbours means insufficient context. Distance and shape are recorded
    for later A/B validation. This function never removes an item.
    """
    if neighbor_count < 1:
        raise ValueError("neighbor_count must be >= 1")

    count = len(spikelets)
    centers = [_centroid_xy(item) for item in spikelets]
    shapes = [spikelet_shape_metrics(item) for item in spikelets]
    records = []

    for index, item in enumerate(spikelets):
        confidence = float(item.get("confidence", 0.0))
        area = float(item["geometry"].area)
        x, y = centers[index]

        ranked = []
        for other_index in range(count):
            if other_index == index:
                continue
            other_confidence = float(
                spikelets[other_index].get("confidence", 0.0)
            )
            if other_confidence < MAX_CONFIDENCE:
                continue
            ox, oy = centers[other_index]
            distance = float(np.hypot(ox - x, oy - y))
            ranked.append((distance, other_index))
        ranked.sort(key=lambda row: (row[0], row[1]))

        selected = ranked[: min(neighbor_count, len(ranked))]
        neighbor_indices = [other_index for _, other_index in selected]
        neighbor_distances = [distance for distance, _ in selected]
        neighbor_areas = [
            float(spikelets[other_index]["geometry"].area)
            for other_index in neighbor_indices
        ]

        enough_context = len(neighbor_indices) >= MIN_NEIGHBORS_FOR_RELATIVE_AREA
        reference_area = float(np.median(neighbor_areas)) if enough_context else None
        relative_area = (
            area / max(1e-9, reference_area)
            if reference_area is not None
            else None
        )
        nearest_distance = float(neighbor_distances[0]) if neighbor_distances else None
        normalized_nearest_distance = (
            nearest_distance / max(1e-9, math.sqrt(reference_area))
            if nearest_distance is not None and reference_area is not None
            else None
        )

        core_suspicious = bool(
            enough_context
            and relative_area is not None
            and relative_area <= MAX_AREA_RATIO_TO_OTHER_MEDIAN
        )
        isolated_small_suspicious = bool(
            enough_context
            and relative_area is not None
            and normalized_nearest_distance is not None
            and relative_area <= EXTENDED_MAX_AREA_RATIO_TO_OTHER_MEDIAN
            and normalized_nearest_distance
            >= EXTENDED_MIN_NORMALIZED_NEAREST_DISTANCE
        )
        if not enough_context:
            status = "insufficient_context"
        elif core_suspicious:
            status = "suspicious"
        else:
            status = "keep"

        records.append(
            {
                "spikelet_index": int(index),
                "status": status,
                "core_suspicious": core_suspicious,
                "isolated_small_suspicious": isolated_small_suspicious,
                "confidence": confidence,
                "area_px2": area,
                "neighbor_count_requested": int(neighbor_count),
                "neighbor_count_used": int(len(neighbor_indices)),
                "neighbor_indices": tuple(int(v) for v in neighbor_indices),
                "neighbor_distances_px": tuple(float(v) for v in neighbor_distances),
                "neighbor_areas_px2": tuple(float(v) for v in neighbor_areas),
                "neighbor_area_median_px2": reference_area,
                "area_ratio_to_neighbor_median": relative_area,
                "nearest_distance_px": nearest_distance,
                "normalized_nearest_distance": normalized_nearest_distance,
                **shapes[index],
            }
        )

    return tuple(records)


def hard_preassociation_cleanup_count_independent(spikelets, grouped):
    """Historical P3-pre v2 fixed-cell cleanup retained for reproducibility."""
    removed = set()
    records = []

    for cell, indices in sorted(grouped.items()):
        if len(indices) < 2:
            continue

        for index in indices:
            confidence = float(spikelets[index].get("confidence", 0.0))
            area = float(spikelets[index]["geometry"].area)
            other_areas = [
                float(spikelets[other_index]["geometry"].area)
                for other_index in indices
                if other_index != index
            ]
            other_median = float(np.median(other_areas))
            area_ratio = area / max(1e-9, other_median)
            reject = (
                confidence < MAX_CONFIDENCE
                and area_ratio <= MAX_AREA_RATIO_TO_OTHER_MEDIAN
            )

            records.append(
                {
                    "cell": [int(cell[0]), int(cell[1])],
                    "spikelet_index_original": int(index),
                    "cell_prediction_count": int(len(indices)),
                    "confidence": confidence,
                    "area_px2": area,
                    "other_area_median_px2": other_median,
                    "area_ratio_to_other_median": area_ratio,
                    "remove_as_hard_false_positive": bool(reject),
                }
            )
            if reject:
                removed.add(index)

    return removed, records


def policy_summary():
    return {
        "role": "development-only count-independent obvious spikelet-fragment cleanup",
        "minimum_cell_prediction_count_for_relative_area_reference": 2,
        "requires_overcomplete_cell": False,
        "max_confidence_strict": MAX_CONFIDENCE,
        "max_area_ratio_to_other_median": MAX_AREA_RATIO_TO_OTHER_MEDIAN,
        "uses_awn_support": False,
        "uses_manual_or_gt": False,
    }


def layout_free_policy_summary():
    return {
        "role": "layout-free spikelet candidate evaluator; characterization only",
        "neighbor_count": DEFAULT_NEIGHBOR_COUNT,
        "reference_neighbor_min_confidence": MAX_CONFIDENCE,
        "minimum_neighbors_for_relative_area_reference": MIN_NEIGHBORS_FOR_RELATIVE_AREA,
        "candidate_confidence_gate_enabled": False,
        "max_area_ratio_to_neighbor_median": MAX_AREA_RATIO_TO_OTHER_MEDIAN,
        "extended_isolated_small_max_area_ratio": (
            EXTENDED_MAX_AREA_RATIO_TO_OTHER_MEDIAN
        ),
        "extended_isolated_small_min_normalized_nearest_distance": (
            EXTENDED_MIN_NORMALIZED_NEAREST_DISTANCE
        ),
        "extended_isolated_small_is_hard_delete": False,
        "distance_metric": "centroid_euclidean_px",
        "normalized_distance_denominator": "sqrt(neighbor_area_median_px2)",
        "shape_metrics": ("rotated_aspect", "solidity", "extent", "compactness"),
        "assumes_fixed_layout": False,
        "uses_accession": False,
        "uses_biological_role": False,
        "uses_awn_support": False,
        "uses_manual_or_gt": False,
        "evaluator_side_effect_free": True,
    }


# ---- page-border diagnostics ---------------------------------------------
BORDER_CONTACT_TOLERANCE_PX = 2.0
BORDER_AXIS_ANGLE_TOLERANCE_DEG = 15.0
BORDER_FOLLOWING_FRACTION_MIN = 0.60
BORDER_BAND_FRACTION = 0.002
BORDER_BAND_MIN_PX = 4.0
BORDER_ARTIFACT_IMPLEMENTATION = "border_following_v3"


class BorderSide(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class BorderArtifactDiagnostic:
    physical_spikelet_id: str
    touches_border: bool
    touched_sides: tuple[BorderSide, ...]
    border_parallel: bool
    border_following_fraction: float
    suspect_border_artifact: bool
    bbox_width_px: float
    bbox_height_px: float
    boundary_distance_px: float


def evaluate_border_artifact(
    *,
    physical_spikelet_id: str,
    geometry,
    page_width_px: int,
    page_height_px: int,
    contact_tolerance_px: float = BORDER_CONTACT_TOLERANCE_PX,
    axis_angle_tolerance_deg: float = BORDER_AXIS_ANGLE_TOLERANCE_DEG,
    following_fraction_min: float = BORDER_FOLLOWING_FRACTION_MIN,
) -> BorderArtifactDiagnostic:
    """Reject a candidate only when it follows a page edge for most of its length.

    The rule intentionally ignores candidate size and local-neighbour status.
    A border artifact must touch the page, have a major axis nearly parallel to
    that edge, and keep a large fraction of its longitudinal span inside a narrow
    edge band.
    """
    width = float(page_width_px)
    height = float(page_height_px)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("page dimensions must be positive")
    tolerance = float(contact_tolerance_px)
    angle_tolerance = float(axis_angle_tolerance_deg)
    following_min = float(following_fraction_min)
    if tolerance < 0.0:
        raise ValueError("contact_tolerance_px must be >= 0")
    if not 0.0 <= angle_tolerance < 90.0:
        raise ValueError("axis_angle_tolerance_deg must be in [0, 90)")
    if not 0.0 < following_min <= 1.0:
        raise ValueError("following_fraction_min must be in (0, 1]")

    min_x, min_y, max_x, max_y = map(float, geometry.bounds)
    bbox_width = max(0.0, max_x - min_x)
    bbox_height = max(0.0, max_y - min_y)
    distances = {
        BorderSide.LEFT: min_x,
        BorderSide.TOP: min_y,
        BorderSide.RIGHT: width - max_x,
        BorderSide.BOTTOM: height - max_y,
    }
    touched = tuple(
        side
        for side, distance in distances.items()
        if distance <= tolerance
    )
    boundary_distance = min(distances.values())

    rect = geometry.minimum_rotated_rectangle
    pts = np.asarray(rect.exterior.coords[:-1], dtype=float)
    vectors = np.roll(pts, -1, axis=0) - pts
    lengths = np.linalg.norm(vectors, axis=1)
    axis = vectors[int(np.argmax(lengths))] if len(vectors) else np.asarray([1.0, 0.0])
    axis_norm = float(np.linalg.norm(axis))
    axis = axis / axis_norm if axis_norm > 0.0 else np.asarray([1.0, 0.0])

    band_px = max(BORDER_BAND_MIN_PX, BORDER_BAND_FRACTION * min(width, height))
    following_fractions = []
    parallel_sides = []
    for side in touched:
        horizontal = side in {BorderSide.TOP, BorderSide.BOTTOM}
        tangent = np.asarray([1.0, 0.0]) if horizontal else np.asarray([0.0, 1.0])
        dot = abs(float(np.dot(axis, tangent)))
        angle = math.degrees(math.acos(max(0.0, min(1.0, dot))))
        if angle > angle_tolerance:
            continue

        if side is BorderSide.LEFT:
            band = box(0.0, 0.0, band_px, height)
            total_span = bbox_height
        elif side is BorderSide.RIGHT:
            band = box(width - band_px, 0.0, width, height)
            total_span = bbox_height
        elif side is BorderSide.TOP:
            band = box(0.0, 0.0, width, band_px)
            total_span = bbox_width
        else:
            band = box(0.0, height - band_px, width, height)
            total_span = bbox_width

        overlap = geometry.intersection(band)
        if overlap.is_empty or total_span <= 0.0:
            fraction = 0.0
        else:
            ov_min_x, ov_min_y, ov_max_x, ov_max_y = map(float, overlap.bounds)
            overlap_span = (
                ov_max_x - ov_min_x
                if horizontal
                else ov_max_y - ov_min_y
            )
            fraction = max(0.0, min(1.0, overlap_span / total_span))
        parallel_sides.append(side)
        following_fractions.append(fraction)

    border_following_fraction = max(following_fractions, default=0.0)
    border_parallel = bool(parallel_sides)
    suspect = bool(
        border_parallel
        and border_following_fraction >= following_min
    )
    return BorderArtifactDiagnostic(
        physical_spikelet_id=str(physical_spikelet_id),
        touches_border=bool(touched),
        touched_sides=touched,
        border_parallel=border_parallel,
        border_following_fraction=float(border_following_fraction),
        suspect_border_artifact=suspect,
        bbox_width_px=bbox_width,
        bbox_height_px=bbox_height,
        boundary_distance_px=float(boundary_distance),
    )


SPIKELET_CLEANUP_IMPLEMENTATION = "phase4c_layout_free_spikelet_cleanup_v1"


class SpikeletCleanupStatus(str, Enum):
    KEEP = "keep"
    REJECTED = "rejected"
    INSUFFICIENT_CONTEXT = "insufficient_context"


@dataclass(frozen=True, slots=True)
class PhysicalSpikeletCleanupDecision:
    decision_id: str
    snapshot_id: SnapshotId
    page_id: str
    physical_spikelet_id: PhysicalSpikeletId
    status: SpikeletCleanupStatus
    source_confidence: float
    area_px2: float
    neighbor_spikelet_ids: tuple[PhysicalSpikeletId, ...]
    neighbor_distances_px: tuple[float, ...]
    neighbor_areas_px2: tuple[float, ...]
    neighbor_area_median_px2: float | None
    area_ratio_to_neighbor_median: float | None
    nearest_distance_px: float | None
    normalized_nearest_distance: float | None
    rotated_aspect: float
    solidity: float
    extent: float
    compactness: float
    isolated_small_suspicious: bool
    provenance: tuple[OperationProvenance, ...] = ()

    def __post_init__(self) -> None:
        page_id = str(self.page_id).strip()
        if not page_id:
            raise ValueError("page_id must not be empty")
        status = (
            self.status
            if isinstance(self.status, SpikeletCleanupStatus)
            else SpikeletCleanupStatus(str(self.status))
        )
        neighbor_ids = tuple(
            PhysicalSpikeletId(str(value))
            for value in self.neighbor_spikelet_ids
        )
        if len(neighbor_ids) != len(set(map(str, neighbor_ids))):
            raise ValueError("neighbor_spikelet_ids must be unique")

        payload = {
            "snapshot_id": str(self.snapshot_id),
            "page_id": page_id,
            "physical_spikelet_id": str(self.physical_spikelet_id),
            "status": status.value,
            "source_confidence": float(self.source_confidence),
            "neighbor_spikelet_ids": [str(value) for value in neighbor_ids],
            "area_ratio_to_neighbor_median": self.area_ratio_to_neighbor_median,
            "normalized_nearest_distance": self.normalized_nearest_distance,
            "implementation": SPIKELET_CLEANUP_IMPLEMENTATION,
        }
        expected_id = (
            f"spkclean_{page_id.lower().replace('_', '-')}_"
            f"{canonical_json_sha256(payload)[:20]}"
        )
        if str(self.decision_id) != expected_id:
            raise ValueError(
                "decision_id does not match spikelet cleanup decision content"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(
            self,
            "physical_spikelet_id",
            PhysicalSpikeletId(str(self.physical_spikelet_id)),
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "neighbor_spikelet_ids", neighbor_ids)
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @property
    def active(self) -> bool:
        return self.status is not SpikeletCleanupStatus.REJECTED


@dataclass(frozen=True, slots=True)
class PhysicalSpikeletCleanupResult:
    page_id: str
    snapshot_id: SnapshotId
    source_physical_spikelet_ids: tuple[PhysicalSpikeletId, ...]
    decisions: tuple[PhysicalSpikeletCleanupDecision, ...]
    active_physical_spikelet_ids: tuple[PhysicalSpikeletId, ...]
    rejected_physical_spikelet_ids: tuple[PhysicalSpikeletId, ...]

    def __post_init__(self) -> None:
        page_id = str(self.page_id).strip()
        if not page_id:
            raise ValueError("page_id must not be empty")

        source = tuple(
            sorted(str(value) for value in self.source_physical_spikelet_ids)
        )
        decision_ids = tuple(
            sorted(str(item.physical_spikelet_id) for item in self.decisions)
        )
        active = tuple(
            sorted(str(value) for value in self.active_physical_spikelet_ids)
        )
        rejected = tuple(
            sorted(str(value) for value in self.rejected_physical_spikelet_ids)
        )
        if len(source) != len(set(source)):
            raise ValueError("source physical spikelet IDs must be unique")
        if source != decision_ids:
            raise ValueError(
                "cleanup decisions must cover source PhysicalSpikelets exactly"
            )
        if set(active) & set(rejected):
            raise ValueError("active/rejected spikelet sets must be disjoint")
        if set(active) | set(rejected) != set(source):
            raise ValueError(
                "active/rejected spikelet sets must partition source IDs"
            )

        object.__setattr__(self, "page_id", page_id)
        object.__setattr__(
            self,
            "source_physical_spikelet_ids",
            tuple(PhysicalSpikeletId(value) for value in source),
        )
        object.__setattr__(
            self,
            "decisions",
            tuple(
                sorted(
                    self.decisions,
                    key=lambda item: str(item.physical_spikelet_id),
                )
            ),
        )
        object.__setattr__(
            self,
            "active_physical_spikelet_ids",
            tuple(PhysicalSpikeletId(value) for value in active),
        )
        object.__setattr__(
            self,
            "rejected_physical_spikelet_ids",
            tuple(PhysicalSpikeletId(value) for value in rejected),
        )


def _source_confidence(
    spikelet: PhysicalSpikelet,
    evidence_by_id: Mapping[str, DetectionEvidence],
) -> float:
    confidences = []
    for evidence_id in spikelet.source_evidence_ids:
        evidence = evidence_by_id.get(str(evidence_id))
        if evidence is None:
            raise ValueError(
                f"missing source evidence for spikelet cleanup: {evidence_id}"
            )
        if evidence.class_name != "spikelet":
            raise ValueError("PhysicalSpikelet source evidence must be spikelet")
        confidences.append(float(evidence.confidence))
    if not confidences:
        raise ValueError("PhysicalSpikelet has no source evidence confidence")
    return max(confidences)


def evaluate_physical_spikelet_cleanup(
    spikelets: Sequence[PhysicalSpikelet],
    evidence: Sequence[DetectionEvidence],
    *,
    neighbor_count: int = DEFAULT_NEIGHBOR_COUNT,
    page_width_px: int | None = None,
    page_height_px: int | None = None,
) -> PhysicalSpikeletCleanupResult:
    ordered = tuple(
        sorted(spikelets, key=lambda item: str(item.physical_spikelet_id))
    )
    if not ordered:
        raise ValueError("spikelet cleanup requires at least one PhysicalSpikelet")

    page_ids = {item.page_id for item in ordered}
    snapshots = {str(item.snapshot_id) for item in ordered}
    if len(page_ids) != 1:
        raise ValueError("spikelet cleanup requires one page")
    if len(snapshots) != 1:
        raise ValueError("spikelet cleanup requires one snapshot")
    if (page_width_px is None) != (page_height_px is None):
        raise ValueError(
            "page_width_px and page_height_px must be provided together"
        )
    if page_width_px is not None:
        if int(page_width_px) <= 0 or int(page_height_px) <= 0:
            raise ValueError("page dimensions must be positive")

    evidence_by_id = {str(item.evidence_id): item for item in evidence}
    items = []
    confidences = []
    for spikelet in ordered:
        confidence = _source_confidence(spikelet, evidence_by_id)
        confidences.append(confidence)
        items.append(
            {
                "geometry": spikelet.geometry,
                "confidence": confidence,
            }
        )

    records = evaluate_layout_free_spikelet_candidates(
        tuple(items),
        neighbor_count=neighbor_count,
    )
    decisions = []
    active_ids = []
    rejected_ids = []

    for index, (spikelet, record) in enumerate(zip(ordered, records)):
        raw_status = str(record["status"])
        status = (
            SpikeletCleanupStatus.REJECTED
            if raw_status == "suspicious"
            else (
                SpikeletCleanupStatus.INSUFFICIENT_CONTEXT
                if raw_status == "insufficient_context"
                else SpikeletCleanupStatus.KEEP
            )
        )
        border_diagnostic = None
        if page_width_px is not None and page_height_px is not None:
            border_diagnostic = evaluate_border_artifact(
                physical_spikelet_id=str(spikelet.physical_spikelet_id),
                geometry=spikelet.geometry,
                page_width_px=int(page_width_px),
                page_height_px=int(page_height_px),
            )
            if border_diagnostic.suspect_border_artifact:
                status = SpikeletCleanupStatus.REJECTED
        neighbor_ids = tuple(
            ordered[int(other_index)].physical_spikelet_id
            for other_index in record["neighbor_indices"]
        )
        payload = {
            "snapshot_id": str(spikelet.snapshot_id),
            "page_id": spikelet.page_id,
            "physical_spikelet_id": str(spikelet.physical_spikelet_id),
            "status": status.value,
            "source_confidence": float(confidences[index]),
            "neighbor_spikelet_ids": [str(value) for value in neighbor_ids],
            "area_ratio_to_neighbor_median": record[
                "area_ratio_to_neighbor_median"
            ],
            "normalized_nearest_distance": record[
                "normalized_nearest_distance"
            ],
            "implementation": SPIKELET_CLEANUP_IMPLEMENTATION,
        }
        decision_id = (
            f"spkclean_{spikelet.page_id.lower().replace('_', '-')}_"
            f"{canonical_json_sha256(payload)[:20]}"
        )
        provenance = OperationProvenance(
            operation="evaluate_physical_spikelet_cleanup",
            implementation=SPIKELET_CLEANUP_IMPLEMENTATION,
            input_ids=(str(spikelet.physical_spikelet_id),),
            output_id=decision_id,
            status=status.value,
            parameters={
                "neighbor_count": int(neighbor_count),
                "legacy_evaluator": (
                    "awnphen.phenotyping.physical.spikelet_cleanup:"
                    "evaluate_layout_free_spikelet_candidates"
                ),
                "hard_reject_status": "suspicious",
                "border_artifact_diagnostic_enabled": (
                    page_width_px is not None
                    and page_height_px is not None
                ),
                "border_artifact_policy": (
                    "touch_border + axis_parallel + high_border_following_fraction"
                ),
            },
            evidence={
                "source_confidence": float(confidences[index]),
                "legacy_record": dict(record),
                "border_artifact": (
                    None
                    if border_diagnostic is None
                    else {
                        "touches_border": border_diagnostic.touches_border,
                        "touched_sides": [
                            side.value
                            for side in border_diagnostic.touched_sides
                        ],
                        "border_parallel": border_diagnostic.border_parallel,
                        "border_following_fraction": (
                            border_diagnostic.border_following_fraction
                        ),
                        "suspect_border_artifact": (
                            border_diagnostic.suspect_border_artifact
                        ),
                        "bbox_width_px": border_diagnostic.bbox_width_px,
                        "bbox_height_px": border_diagnostic.bbox_height_px,
                        "boundary_distance_px": (
                            border_diagnostic.boundary_distance_px
                        ),
                    }
                ),
                "reject_reason": (
                    "relative_area"
                    if raw_status == "suspicious"
                    else (
                        "border_artifact"
                        if (
                            border_diagnostic is not None
                            and border_diagnostic.suspect_border_artifact
                        )
                        else None
                    )
                ),
            },
        )
        decision = PhysicalSpikeletCleanupDecision(
            decision_id=decision_id,
            snapshot_id=spikelet.snapshot_id,
            page_id=spikelet.page_id,
            physical_spikelet_id=spikelet.physical_spikelet_id,
            status=status,
            source_confidence=float(confidences[index]),
            area_px2=float(record["area_px2"]),
            neighbor_spikelet_ids=neighbor_ids,
            neighbor_distances_px=tuple(
                float(value) for value in record["neighbor_distances_px"]
            ),
            neighbor_areas_px2=tuple(
                float(value) for value in record["neighbor_areas_px2"]
            ),
            neighbor_area_median_px2=(
                None
                if record["neighbor_area_median_px2"] is None
                else float(record["neighbor_area_median_px2"])
            ),
            area_ratio_to_neighbor_median=(
                None
                if record["area_ratio_to_neighbor_median"] is None
                else float(record["area_ratio_to_neighbor_median"])
            ),
            nearest_distance_px=(
                None
                if record["nearest_distance_px"] is None
                else float(record["nearest_distance_px"])
            ),
            normalized_nearest_distance=(
                None
                if record["normalized_nearest_distance"] is None
                else float(record["normalized_nearest_distance"])
            ),
            rotated_aspect=float(record["rotated_aspect"]),
            solidity=float(record["solidity"]),
            extent=float(record["extent"]),
            compactness=float(record["compactness"]),
            isolated_small_suspicious=bool(
                record["isolated_small_suspicious"]
            ),
            provenance=(provenance,),
        )
        decisions.append(decision)
        if decision.active:
            active_ids.append(spikelet.physical_spikelet_id)
        else:
            rejected_ids.append(spikelet.physical_spikelet_id)

    return PhysicalSpikeletCleanupResult(
        page_id=ordered[0].page_id,
        snapshot_id=ordered[0].snapshot_id,
        source_physical_spikelet_ids=tuple(
            item.physical_spikelet_id for item in ordered
        ),
        decisions=tuple(decisions),
        active_physical_spikelet_ids=tuple(active_ids),
        rejected_physical_spikelet_ids=tuple(rejected_ids),
    )


__all__ = [
    "MAX_CONFIDENCE",
    "MAX_AREA_RATIO_TO_OTHER_MEDIAN",
    "EXTENDED_MAX_AREA_RATIO_TO_OTHER_MEDIAN",
    "EXTENDED_MIN_NORMALIZED_NEAREST_DISTANCE",
    "DEFAULT_NEIGHBOR_COUNT",
    "MIN_NEIGHBORS_FOR_RELATIVE_AREA",
    "spikelet_shape_metrics",
    "evaluate_layout_free_spikelet_candidates",
    "hard_preassociation_cleanup_count_independent",
    "policy_summary",
    "layout_free_policy_summary",
    "BORDER_ARTIFACT_IMPLEMENTATION",
    "BORDER_CONTACT_TOLERANCE_PX",
    "BORDER_AXIS_ANGLE_TOLERANCE_DEG",
    "BORDER_FOLLOWING_FRACTION_MIN",
    "BORDER_BAND_FRACTION",
    "BORDER_BAND_MIN_PX",
    "BorderArtifactDiagnostic",
    "BorderSide",
    "evaluate_border_artifact",
    "SPIKELET_CLEANUP_IMPLEMENTATION",
    "SpikeletCleanupStatus",
    "PhysicalSpikeletCleanupDecision",
    "PhysicalSpikeletCleanupResult",
    "evaluate_physical_spikelet_cleanup",
]
