"""Phase 3 instance reconciliation for immutable DetectionEvidence.

This module unifies the historical cross-tile merge and class-specific dedupe
semantics without deleting raw evidence. Strong duplicate relations may form an
InstanceHypothesis. Ambiguous relations remain explicit and are never silently
collapsed.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from shapely import box
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from awnphen.core.domain.physical import DetectionEvidence, HypothesisStatus, InstanceHypothesis
from awnphen.core.domain.physical_provenance import (
    EvidenceId,
    OperationProvenance,
    SnapshotId,
    canonical_json_sha256,
)

RECONCILIATION_IMPLEMENTATION = "awnphen_next.instance_reconciliation_v1"
RECONCILIATION_FILE_SCHEMA = "awnphen_instance_reconciliation_v1"


class PairDecisionStatus(str, Enum):
    STRONG_DUPLICATE = "strong_duplicate"
    AMBIGUOUS = "ambiguous"
    DISTINCT = "distinct"


@dataclass(frozen=True, slots=True)
class ClassReconciliationThresholds:
    duplicate_iou: float
    duplicate_overlap: float
    duplicate_buffer: float
    same_tile_max_axis_angle: float | None = None
    same_tile_min_overlap: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "duplicate_iou": self.duplicate_iou,
            "duplicate_overlap": self.duplicate_overlap,
            "duplicate_buffer": self.duplicate_buffer,
            "same_tile_max_axis_angle": self.same_tile_max_axis_angle,
            "same_tile_min_overlap": self.same_tile_min_overlap,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationConfig:
    awn: ClassReconciliationThresholds = ClassReconciliationThresholds(
        duplicate_iou=0.28,
        duplicate_overlap=0.62,
        duplicate_buffer=3.0,
        same_tile_max_axis_angle=1.5,
        same_tile_min_overlap=0.94,
    )
    spikelet: ClassReconciliationThresholds = ClassReconciliationThresholds(
        duplicate_iou=0.30,
        duplicate_overlap=0.65,
        duplicate_buffer=2.0,
    )
    cross_tile_overlap_min: float = 0.45
    cross_tile_shared_iou_min: float = 0.35
    cross_tile_intersection_area_min: float = 8.0
    cross_tile_shared_extent_min: float = 24.0
    cross_tile_awn_max_axis_angle_deg: float | None = None
    ambiguous_fraction: float = 0.75
    awn_width_inflation_max: float = 2.8
    awn_axis_drift_max_deg: float = 30.0
    awn_component_count_max: int = 3
    awn_branchpoint_excess_max: int = 8
    awn_endpoint_excess_max: int = 6
    spikelet_component_count_max: int = 3
    spikelet_area_inflation_max: float = 2.8

    def thresholds_for(self, class_name: str) -> ClassReconciliationThresholds:
        if class_name == "awn":
            return self.awn
        if class_name == "spikelet":
            return self.spikelet
        raise ValueError(f"unsupported class_name: {class_name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "awn": self.awn.to_dict(),
            "spikelet": self.spikelet.to_dict(),
            "cross_tile_overlap_min": self.cross_tile_overlap_min,
            "cross_tile_shared_iou_min": self.cross_tile_shared_iou_min,
            "cross_tile_intersection_area_min": self.cross_tile_intersection_area_min,
            "cross_tile_shared_extent_min": self.cross_tile_shared_extent_min,
            "cross_tile_awn_max_axis_angle_deg": self.cross_tile_awn_max_axis_angle_deg,
            "ambiguous_fraction": self.ambiguous_fraction,
            "awn_width_inflation_max": self.awn_width_inflation_max,
            "awn_axis_drift_max_deg": self.awn_axis_drift_max_deg,
            "awn_component_count_max": self.awn_component_count_max,
            "awn_branchpoint_excess_max": self.awn_branchpoint_excess_max,
            "awn_endpoint_excess_max": self.awn_endpoint_excess_max,
            "spikelet_component_count_max": self.spikelet_component_count_max,
            "spikelet_area_inflation_max": self.spikelet_area_inflation_max,
        }


@dataclass(frozen=True, slots=True)
class PairFeatures:
    distance_px: float
    intersection_area_px2: float
    overlap_min: float
    iou: float
    buffered_overlap_min: float
    buffered_iou: float
    same_tile: bool
    tile_windows_overlap: bool
    shared_window_iou: float
    shared_extent_px: float
    axis_angle_deg: float
    endpoint_distance_px: float
    confidence_min: float
    confidence_max: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "distance_px": self.distance_px,
            "intersection_area_px2": self.intersection_area_px2,
            "overlap_min": self.overlap_min,
            "iou": self.iou,
            "buffered_overlap_min": self.buffered_overlap_min,
            "buffered_iou": self.buffered_iou,
            "same_tile": self.same_tile,
            "tile_windows_overlap": self.tile_windows_overlap,
            "shared_window_iou": self.shared_window_iou,
            "shared_extent_px": self.shared_extent_px,
            "axis_angle_deg": self.axis_angle_deg,
            "endpoint_distance_px": self.endpoint_distance_px,
            "confidence_min": self.confidence_min,
            "confidence_max": self.confidence_max,
        }


@dataclass(frozen=True, slots=True)
class _CachedEvidenceFeatures:
    principal_axis: np.ndarray
    endpoints: tuple[np.ndarray, np.ndarray]
    buffered_geometry: BaseGeometry
    tile_box: BaseGeometry | None
    memo_key: tuple | None = field(default=None, repr=False, compare=False)


@dataclass(slots=True)
class _ReconciliationComputationCache:
    """Transient, content-keyed geometry memo for one pipeline invocation."""

    evidence_features: dict = field(default_factory=dict)
    pair_features: dict = field(default_factory=dict)
    shared_windows: dict = field(default_factory=dict)
    shared_clips: dict = field(default_factory=dict)


_COMPUTATION_CACHE: ContextVar[_ReconciliationComputationCache | None] = (
    ContextVar("reconciliation_memo", default=None)
)


@contextmanager
def reconciliation_computation_cache():
    """Reuse exact geometry computations without caching policy decisions.

    Nested reconciliation calls share the enclosing task's memo. ContextVar
    keeps concurrent jobs isolated; resetting the token releases the memo on
    normal return and on exceptions. Geometry WKB and evidence metadata are
    part of the keys, so reloaded snapshots can share computations safely.
    """
    existing = _COMPUTATION_CACHE.get()
    if existing is not None:
        yield existing
        return
    memo = _ReconciliationComputationCache()
    reset_handle = _COMPUTATION_CACHE.set(memo)
    try:
        yield memo
    finally:
        _COMPUTATION_CACHE.reset(reset_handle)


def _build_pair_feature_cache(
    evidence: Sequence[DetectionEvidence],
    *,
    config: ReconciliationConfig,
) -> dict[str, _CachedEvidenceFeatures]:
    cache: dict[str, _CachedEvidenceFeatures] = {}
    memo = _COMPUTATION_CACHE.get()
    for item in evidence:
        thresholds = config.thresholds_for(item.class_name)
        tile = _tile_box(item)
        memo_key = (
            str(item.snapshot_id), str(item.evidence_id),
            item.class_id, item.class_name, item.geometry.wkb,
            item.source_tile_id, float(item.confidence),
            None if tile is None else tile.wkb,
            float(thresholds.duplicate_buffer),
        ) if memo is not None else None
        if memo is not None and memo_key in memo.evidence_features:
            cache[str(item.evidence_id)] = memo.evidence_features[memo_key]
            continue
        cached = _CachedEvidenceFeatures(
            principal_axis=_principal_axis(item.geometry),
            endpoints=_pca_endpoints(item.geometry),
            buffered_geometry=item.geometry.buffer(thresholds.duplicate_buffer),
            tile_box=tile,
            memo_key=memo_key,
        )
        cache[str(item.evidence_id)] = cached
        if memo is not None:
            memo.evidence_features[memo_key] = cached
    return cache


def _pair_id(snapshot_id: str, page_id: str, left_id: str, right_id: str) -> str:
    a, b = sorted((str(left_id), str(right_id)))
    digest = canonical_json_sha256(
        {
            "namespace": "reconciliation_pair",
            "snapshot_id": str(snapshot_id),
            "page_id": str(page_id),
            "evidence_ids": [a, b],
        }
    )[:20]
    return f"pair_{digest}"


@dataclass(frozen=True, slots=True)
class PairDecision:
    pair_id: str
    snapshot_id: SnapshotId
    page_id: str
    class_name: str
    left_evidence_id: EvidenceId
    right_evidence_id: EvidenceId
    status: PairDecisionStatus
    reason: str
    strength: float
    features: PairFeatures
    provenance: OperationProvenance

    def __post_init__(self) -> None:
        left, right = sorted((str(self.left_evidence_id), str(self.right_evidence_id)))
        if left == right:
            raise ValueError("pair decision requires two distinct evidence IDs")
        expected = _pair_id(str(self.snapshot_id), self.page_id, left, right)
        if self.pair_id != expected:
            raise ValueError("pair_id does not match evidence pair identity")
        object.__setattr__(self, "left_evidence_id", EvidenceId(left))
        object.__setattr__(self, "right_evidence_id", EvidenceId(right))
        object.__setattr__(
            self,
            "status",
            self.status
            if isinstance(self.status, PairDecisionStatus)
            else PairDecisionStatus(str(self.status)),
        )
        strength = float(self.strength)
        if not math.isfinite(strength) or strength < 0:
            raise ValueError("pair strength must be finite and >= 0")
        object.__setattr__(self, "strength", strength)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    page_id: str
    snapshot_id: SnapshotId
    source_evidence_ids: tuple[EvidenceId, ...]
    pair_decisions: tuple[PairDecision, ...]
    hypotheses: tuple[InstanceHypothesis, ...]
    hypothesis_diagnostics: Mapping[str, Mapping[str, Any]]
    config_payload: Mapping[str, Any]
    config_sha256: str
    blocked_strong_pair_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        source_ids = tuple(sorted(str(v) for v in self.source_evidence_ids))
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_evidence_ids must be unique")
        object.__setattr__(
            self,
            "source_evidence_ids",
            tuple(EvidenceId(v) for v in source_ids),
        )
        pair_ids = [item.pair_id for item in self.pair_decisions]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pair_decisions must have unique pair_id values")

        assigned = [
            str(evidence_id)
            for hypothesis in self.hypotheses
            for evidence_id in hypothesis.evidence_ids
        ]
        if sorted(assigned) != list(source_ids):
            raise ValueError(
                "hypotheses must partition source evidence exactly once"
            )
        for hypothesis in self.hypotheses:
            if hypothesis.page_id != self.page_id:
                raise ValueError("hypothesis page_id mismatch")
            if hypothesis.snapshot_id != self.snapshot_id:
                raise ValueError("hypothesis snapshot_id mismatch")

        diagnostics = {
            str(key): MappingProxyType(dict(value))
            for key, value in self.hypothesis_diagnostics.items()
        }
        if set(diagnostics) != {
            str(item.hypothesis_id) for item in self.hypotheses
        }:
            raise ValueError("hypothesis_diagnostics must cover all hypotheses")
        object.__setattr__(
            self,
            "hypothesis_diagnostics",
            MappingProxyType(diagnostics),
        )
        config_payload = MappingProxyType(dict(self.config_payload))
        if canonical_json_sha256(config_payload) != self.config_sha256:
            raise ValueError("config_sha256 does not match config_payload")
        object.__setattr__(self, "config_payload", config_payload)
        object.__setattr__(
            self,
            "blocked_strong_pair_ids",
            tuple(sorted(set(self.blocked_strong_pair_ids))),
        )


def _parts(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > 1e-9 else []
    if isinstance(geometry, MultiPolygon):
        return [item for item in geometry.geoms if item.area > 1e-9]
    if isinstance(geometry, GeometryCollection):
        return [
            polygon
            for item in geometry.geoms
            for polygon in _parts(item)
        ]
    return []


def _bounds_distance(a: BaseGeometry, b: BaseGeometry) -> float:
    ax1, ay1, ax2, ay2 = a.bounds
    bx1, by1, bx2, by2 = b.bounds
    dx = max(0.0, bx1 - ax2, ax1 - bx2)
    dy = max(0.0, by1 - ay2, ay1 - by2)
    return float(math.hypot(dx, dy))


def _intersection_stats(
    a: BaseGeometry,
    b: BaseGeometry,
    *,
    buffer_px: float = 0.0,
) -> tuple[float, float, float]:
    ga = a.buffer(buffer_px) if buffer_px else a
    gb = b.buffer(buffer_px) if buffer_px else b
    if not ga.intersects(gb):
        return 0.0, 0.0, 0.0
    intersection = ga.intersection(gb).area
    union = ga.area + gb.area - intersection
    iou = intersection / max(1e-9, union)
    overlap_min = intersection / max(1e-9, min(ga.area, gb.area))
    return float(intersection), float(iou), float(overlap_min)


def _principal_axis(geometry: BaseGeometry) -> np.ndarray:
    polygons = _parts(geometry)
    coords = [
        np.asarray(polygon.exterior.coords, dtype=float)[:-1, :2]
        for polygon in polygons
        if len(polygon.exterior.coords) >= 3
    ]
    if not coords:
        return np.asarray([1.0, 0.0], dtype=float)
    values = np.concatenate(coords, axis=0)
    if len(values) < 2:
        return np.asarray([1.0, 0.0], dtype=float)
    centered = values - values.mean(axis=0)
    covariance = np.cov(centered, rowvar=False)
    if np.ndim(covariance) != 2 or covariance.shape != (2, 2):
        return np.asarray([1.0, 0.0], dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-9:
        return np.asarray([1.0, 0.0], dtype=float)
    return axis / norm


def _axis_angle_deg(a: BaseGeometry, b: BaseGeometry) -> float:
    axis_a = _principal_axis(a)
    axis_b = _principal_axis(b)
    dot = float(np.clip(abs(np.dot(axis_a, axis_b)), 0.0, 1.0))
    return float(math.degrees(math.acos(dot)))


def _pca_endpoints(geometry: BaseGeometry) -> tuple[np.ndarray, np.ndarray]:
    polygons = _parts(geometry)
    coords = [
        np.asarray(polygon.exterior.coords, dtype=float)[:-1, :2]
        for polygon in polygons
        if len(polygon.exterior.coords) >= 3
    ]
    if not coords:
        point = np.asarray(geometry.representative_point().coords[0], dtype=float)
        return point, point
    values = np.concatenate(coords, axis=0)
    axis = _principal_axis(geometry)
    center = values.mean(axis=0)
    projections = (values - center) @ axis
    return values[int(np.argmin(projections))], values[int(np.argmax(projections))]


def _endpoint_distance(a: BaseGeometry, b: BaseGeometry) -> float:
    a0, a1 = _pca_endpoints(a)
    b0, b1 = _pca_endpoints(b)
    return float(
        min(
            np.linalg.norm(a0 - b0),
            np.linalg.norm(a0 - b1),
            np.linalg.norm(a1 - b0),
            np.linalg.norm(a1 - b1),
        )
    )


def _evidence_metadata(item: DetectionEvidence, key: str) -> Any:
    for record in reversed(item.provenance):
        if key in record.evidence:
            return record.evidence[key]
    return None


def _tile_box(item: DetectionEvidence) -> BaseGeometry | None:
    value = _evidence_metadata(item, "tile_xyxy")
    if value is None:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in value)
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return box(x1, y1, x2, y2)


def _shared_window_metrics(
    left: DetectionEvidence,
    right: DetectionEvidence,
) -> tuple[bool, float, float]:
    left_tile = _tile_box(left)
    right_tile = _tile_box(right)
    if left_tile is None or right_tile is None:
        return False, 0.0, 0.0
    shared = left_tile.intersection(right_tile)
    if shared.is_empty or shared.area <= 0:
        return False, 0.0, 0.0
    ga = left.geometry.intersection(shared)
    gb = right.geometry.intersection(shared)
    union_area = ga.union(gb).area
    intersection = left.geometry.intersection(right.geometry)
    if intersection.is_empty:
        return True, 0.0, 0.0
    local_iou = intersection.area / max(1e-9, union_area)
    minx, miny, maxx, maxy = intersection.bounds
    shared_extent = max(maxx - minx, maxy - miny)
    return True, float(local_iou), float(shared_extent)


def pair_features(
    left: DetectionEvidence,
    right: DetectionEvidence,
    *,
    buffer_px: float,
    feature_cache: Mapping[str, _CachedEvidenceFeatures] | None = None,
) -> PairFeatures:
    memo = _COMPUTATION_CACHE.get()
    pair_key = None
    if memo is not None and feature_cache is not None:
        left_key = feature_cache[str(left.evidence_id)].memo_key
        right_key = feature_cache[str(right.evidence_id)].memo_key
        if left_key is not None and right_key is not None:
            pair_key = (left_key, right_key, float(buffer_px))
            if pair_key in memo.pair_features:
                return memo.pair_features[pair_key]
    if feature_cache is None:
        intersection_area, iou, overlap_min = _intersection_stats(
            left.geometry, right.geometry
        )
        _, buffered_iou, buffered_overlap = _intersection_stats(
            left.geometry,
            right.geometry,
            buffer_px=buffer_px,
        )
        windows_overlap, shared_iou, shared_extent = _shared_window_metrics(
            left, right
        )
        axis_angle = _axis_angle_deg(left.geometry, right.geometry)
        endpoint_distance = _endpoint_distance(left.geometry, right.geometry)
    else:
        left_cached = feature_cache[str(left.evidence_id)]
        right_cached = feature_cache[str(right.evidence_id)]

        raw_intersection = left.geometry.intersection(right.geometry)
        intersection_area = float(raw_intersection.area)
        raw_union_area = left.geometry.area + right.geometry.area - intersection_area
        iou = intersection_area / max(1e-9, raw_union_area)
        overlap_min = intersection_area / max(
            1e-9, min(left.geometry.area, right.geometry.area)
        )

        buffered_left = left_cached.buffered_geometry
        buffered_right = right_cached.buffered_geometry
        buffered_intersection_area = buffered_left.intersection(
            buffered_right
        ).area
        buffered_union_area = (
            buffered_left.area
            + buffered_right.area
            - buffered_intersection_area
        )
        buffered_iou = buffered_intersection_area / max(
            1e-9, buffered_union_area
        )
        buffered_overlap = buffered_intersection_area / max(
            1e-9, min(buffered_left.area, buffered_right.area)
        )

        left_tile = left_cached.tile_box
        right_tile = right_cached.tile_box
        if left_tile is None or right_tile is None:
            windows_overlap, shared_iou, shared_extent = False, 0.0, 0.0
        else:
            window_key = (left_tile.wkb, right_tile.wkb)
            if memo is not None and window_key in memo.shared_windows:
                shared = memo.shared_windows[window_key]
            else:
                shared = left_tile.intersection(right_tile)
                if memo is not None:
                    memo.shared_windows[window_key] = shared
            if shared.is_empty or shared.area <= 0:
                windows_overlap, shared_iou, shared_extent = False, 0.0, 0.0
            elif raw_intersection.is_empty:
                windows_overlap, shared_iou, shared_extent = True, 0.0, 0.0
            else:
                shared_wkb = shared.wkb
                left_clip_key = (left_cached.memo_key, shared_wkb)
                right_clip_key = (right_cached.memo_key, shared_wkb)
                if memo is not None and left_clip_key in memo.shared_clips:
                    left_shared = memo.shared_clips[left_clip_key]
                else:
                    left_shared = left.geometry.intersection(shared)
                    if memo is not None and left_cached.memo_key is not None:
                        memo.shared_clips[left_clip_key] = left_shared
                if memo is not None and right_clip_key in memo.shared_clips:
                    right_shared = memo.shared_clips[right_clip_key]
                else:
                    right_shared = right.geometry.intersection(shared)
                    if memo is not None and right_cached.memo_key is not None:
                        memo.shared_clips[right_clip_key] = right_shared
                shared_union_area = left_shared.union(right_shared).area
                shared_iou = intersection_area / max(1e-9, shared_union_area)
                minx, miny, maxx, maxy = raw_intersection.bounds
                shared_extent = max(maxx - minx, maxy - miny)
                windows_overlap = True

        dot = float(
            np.clip(
                abs(
                    np.dot(
                        left_cached.principal_axis,
                        right_cached.principal_axis,
                    )
                ),
                0.0,
                1.0,
            )
        )
        axis_angle = float(math.degrees(math.acos(dot)))

        left0, left1 = left_cached.endpoints
        right0, right1 = right_cached.endpoints
        endpoint_distance = float(
            min(
                np.linalg.norm(left0 - right0),
                np.linalg.norm(left0 - right1),
                np.linalg.norm(left1 - right0),
                np.linalg.norm(left1 - right1),
            )
        )

    result = PairFeatures(
        distance_px=_bounds_distance(left.geometry, right.geometry),
        intersection_area_px2=float(intersection_area),
        overlap_min=float(overlap_min),
        iou=float(iou),
        buffered_overlap_min=float(buffered_overlap),
        buffered_iou=float(buffered_iou),
        same_tile=left.source_tile_id == right.source_tile_id,
        tile_windows_overlap=windows_overlap,
        shared_window_iou=float(shared_iou),
        shared_extent_px=float(shared_extent),
        axis_angle_deg=axis_angle,
        endpoint_distance_px=endpoint_distance,
        confidence_min=min(left.confidence, right.confidence),
        confidence_max=max(left.confidence, right.confidence),
    )
    if memo is not None and pair_key is not None:
        memo.pair_features[pair_key] = result
    return result


def _candidate_pair(
    left: DetectionEvidence,
    right: DetectionEvidence,
    thresholds: ClassReconciliationThresholds,
) -> bool:
    if left.class_id != right.class_id:
        return False
    distance = _bounds_distance(left.geometry, right.geometry)
    if distance <= 2.0 * thresholds.duplicate_buffer:
        return True
    if left.source_tile_id == right.source_tile_id:
        return False
    left_tile = _tile_box(left)
    right_tile = _tile_box(right)
    if left_tile is None or right_tile is None:
        return False
    if left_tile.intersection(right_tile).is_empty:
        return False
    ax1, ay1, ax2, ay2 = left.geometry.bounds
    bx1, by1, bx2, by2 = right.geometry.bounds
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


def classify_pair(
    left: DetectionEvidence,
    right: DetectionEvidence,
    *,
    config: ReconciliationConfig,
    feature_cache: Mapping[str, _CachedEvidenceFeatures] | None = None,
) -> PairDecision:
    if left.snapshot_id != right.snapshot_id or left.page_id != right.page_id:
        raise ValueError("pair evidence must share page and snapshot")
    if left.class_id != right.class_id:
        raise ValueError("pair evidence must share class")

    thresholds = config.thresholds_for(left.class_name)
    features = pair_features(
        left,
        right,
        buffer_px=thresholds.duplicate_buffer,
        feature_cache=feature_cache,
    )

    cross_tile_match = (
        not features.same_tile
        and features.tile_windows_overlap
        and features.intersection_area_px2
        >= config.cross_tile_intersection_area_min
        and features.overlap_min >= config.cross_tile_overlap_min
        and features.shared_window_iou
        >= config.cross_tile_shared_iou_min
        and features.shared_extent_px
        >= config.cross_tile_shared_extent_min
        and (
            left.class_name != "awn"
            or config.cross_tile_awn_max_axis_angle_deg is None
            or features.axis_angle_deg <= config.cross_tile_awn_max_axis_angle_deg
        )
    )

    dedupe_match = (
        features.buffered_iou >= thresholds.duplicate_iou
        or features.buffered_overlap_min >= thresholds.duplicate_overlap
    )

    same_tile_exception = True
    if features.same_tile and left.class_name == "awn":
        same_tile_exception = (
            thresholds.same_tile_max_axis_angle is not None
            and features.axis_angle_deg <= thresholds.same_tile_max_axis_angle
            and features.buffered_overlap_min
            >= thresholds.same_tile_min_overlap
        )

    if cross_tile_match or (dedupe_match and same_tile_exception):
        status = PairDecisionStatus.STRONG_DUPLICATE
        reason = (
            "cross_tile_overlap"
            if cross_tile_match
            else "buffered_duplicate"
        )
    else:
        fraction = config.ambiguous_fraction
        near_dedupe = (
            features.buffered_iou
            >= thresholds.duplicate_iou * fraction
            or features.buffered_overlap_min
            >= thresholds.duplicate_overlap * fraction
        )
        near_cross_tile = (
            not features.same_tile
            and features.tile_windows_overlap
            and features.intersection_area_px2
            >= config.cross_tile_intersection_area_min * fraction
            and features.overlap_min
            >= config.cross_tile_overlap_min * fraction
            and features.shared_window_iou
            >= config.cross_tile_shared_iou_min * fraction
            and features.shared_extent_px
            >= config.cross_tile_shared_extent_min * fraction
        )
        same_tile_awn_ambiguous = (
            features.same_tile
            and left.class_name == "awn"
            and features.buffered_overlap_min >= 0.75
            and features.axis_angle_deg <= 8.0
        )
        if near_dedupe or near_cross_tile or same_tile_awn_ambiguous:
            status = PairDecisionStatus.AMBIGUOUS
            reason = (
                "same_tile_near_duplicate"
                if same_tile_awn_ambiguous
                else "near_duplicate"
            )
        else:
            status = PairDecisionStatus.DISTINCT
            reason = (
                "same_tile_coexistence"
                if features.same_tile
                else "geometry_incompatible"
            )

    strength = max(
        features.buffered_iou / max(thresholds.duplicate_iou, 1e-9),
        features.buffered_overlap_min
        / max(thresholds.duplicate_overlap, 1e-9),
        features.overlap_min / max(config.cross_tile_overlap_min, 1e-9),
        features.shared_window_iou
        / max(config.cross_tile_shared_iou_min, 1e-9),
    )
    left_id, right_id = sorted(
        (str(left.evidence_id), str(right.evidence_id))
    )
    pair_id = _pair_id(
        str(left.snapshot_id), left.page_id, left_id, right_id
    )
    provenance = OperationProvenance(
        operation="classify_evidence_pair",
        implementation=RECONCILIATION_IMPLEMENTATION,
        input_ids=(left_id, right_id),
        output_id=pair_id,
        status=status.value,
        parameters={
            "reason": reason,
            "class_name": left.class_name,
        },
        evidence=features.to_dict(),
    )
    return PairDecision(
        pair_id=pair_id,
        snapshot_id=left.snapshot_id,
        page_id=left.page_id,
        class_name=left.class_name,
        left_evidence_id=EvidenceId(left_id),
        right_evidence_id=EvidenceId(right_id),
        status=status,
        reason=reason,
        strength=strength,
        features=features,
        provenance=provenance,
    )


def generate_pair_decisions(
    evidence: Sequence[DetectionEvidence],
    *,
    config: ReconciliationConfig,
    use_spatial_index: bool = True,
    use_feature_cache: bool = True,
) -> tuple[PairDecision, ...]:
    ordered = sorted(evidence, key=lambda item: str(item.evidence_id))
    decisions: list[PairDecision] = []
    feature_cache = (
        _build_pair_feature_cache(ordered, config=config)
        if use_feature_cache and len(ordered) >= 2
        else None
    )

    if not use_spatial_index or len(ordered) < 2:
        for index, left in enumerate(ordered):
            thresholds = config.thresholds_for(left.class_name)
            for right in ordered[index + 1 :]:
                if left.class_id != right.class_id:
                    continue
                if not _candidate_pair(left, right, thresholds):
                    continue
                decisions.append(
                    classify_pair(
                        left,
                        right,
                        config=config,
                        feature_cache=feature_cache,
                    )
                )
        return tuple(sorted(decisions, key=lambda item: item.pair_id))

    # Spatial indexing is an exact candidate-generation optimization only.
    # Query an expanded bounds envelope that is guaranteed to contain every
    # pair accepted by _candidate_pair(). Scientific pair classification is
    # intentionally unchanged.
    geometries = [item.geometry for item in ordered]
    tree = STRtree(geometries)
    for index, left in enumerate(ordered):
        thresholds = config.thresholds_for(left.class_name)
        minx, miny, maxx, maxy = left.geometry.bounds
        padding = 2.0 * thresholds.duplicate_buffer
        query_geometry = box(
            minx - padding,
            miny - padding,
            maxx + padding,
            maxy + padding,
        )
        candidate_indices = sorted(
            int(value)
            for value in tree.query(query_geometry)
            if int(value) > index
        )
        for right_index in candidate_indices:
            right = ordered[right_index]
            if left.class_id != right.class_id:
                continue
            if not _candidate_pair(left, right, thresholds):
                continue
            decisions.append(
                classify_pair(
                    left,
                    right,
                    config=config,
                    feature_cache=feature_cache,
                )
            )
    return tuple(sorted(decisions, key=lambda item: item.pair_id))


def _component_count(geometry: BaseGeometry) -> int:
    return len(_parts(geometry))


def _major_span(geometry: BaseGeometry) -> float:
    polygons = _parts(geometry)
    if not polygons:
        return 1.0
    coords = np.concatenate(
        [
            np.asarray(item.exterior.coords, dtype=float)[:-1, :2]
            for item in polygons
        ],
        axis=0,
    )
    axis = _principal_axis(geometry)
    projections = coords @ axis
    return max(1.0, float(projections.max() - projections.min()))


def _effective_width(geometry: BaseGeometry) -> float:
    return float(geometry.area / _major_span(geometry))


def _skeleton_topology(geometry: BaseGeometry) -> tuple[int, int]:
    polygons = _parts(geometry)
    if not polygons:
        return 0, 0
    minx, miny, maxx, maxy = geometry.bounds
    pad = 2
    x0 = int(math.floor(minx)) - pad
    y0 = int(math.floor(miny)) - pad
    x1 = int(math.ceil(maxx)) + pad
    y1 = int(math.ceil(maxy)) + pad
    width = max(1, x1 - x0 + 1)
    height = max(1, y1 - y0 + 1)
    if width * height > 4_000_000:
        scale = math.sqrt(4_000_000 / float(width * height))
    else:
        scale = 1.0
    raster_w = max(1, int(round(width * scale)))
    raster_h = max(1, int(round(height * scale)))
    mask = np.zeros((raster_h, raster_w), dtype=np.uint8)
    for polygon in polygons:
        points = np.asarray(polygon.exterior.coords, dtype=float)[:, :2]
        points[:, 0] = (points[:, 0] - x0) * scale
        points[:, 1] = (points[:, 1] - y0) * scale
        cv2.fillPoly(mask, [np.rint(points).astype(np.int32)], 255)
        for interior in polygon.interiors:
            hole = np.asarray(interior.coords, dtype=float)[:, :2]
            hole[:, 0] = (hole[:, 0] - x0) * scale
            hole[:, 1] = (hole[:, 1] - y0) * scale
            cv2.fillPoly(mask, [np.rint(hole).astype(np.int32)], 0)

    work = mask.copy()
    skeleton = np.zeros_like(work)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(work):
        eroded = cv2.erode(work, kernel)
        opened = cv2.dilate(eroded, kernel)
        skeleton = cv2.bitwise_or(
            skeleton, cv2.subtract(work, opened)
        )
        work = eroded
    binary = (skeleton > 0).astype(np.uint8)
    if not binary.any():
        return 0, 0
    neighbor_count = cv2.filter2D(
        binary,
        cv2.CV_16U,
        np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
    ) - binary
    endpoint_mask = ((binary > 0) & (neighbor_count <= 1)).astype(np.uint8)
    branch_mask = ((binary > 0) & (neighbor_count >= 3)).astype(np.uint8)
    # A single structural branch can occupy many adjacent skeleton pixels.
    # Count connected branch/end-point regions rather than raw pixels.
    endpoints = max(
        0,
        int(cv2.connectedComponents(endpoint_mask, connectivity=8)[0]) - 1,
    )
    if branch_mask.any():
        branch_mask = cv2.dilate(
            branch_mask,
            np.ones((3, 3), dtype=np.uint8),
            iterations=1,
        )
    branchpoints = max(
        0,
        int(cv2.connectedComponents(branch_mask, connectivity=8)[0]) - 1,
    )
    return endpoints, branchpoints


def fusion_sanity(
    members: Sequence[DetectionEvidence],
    union_geometry: BaseGeometry,
    *,
    config: ReconciliationConfig,
) -> tuple[bool, dict[str, Any]]:
    if not members:
        raise ValueError("fusion_sanity requires members")
    class_name = members[0].class_name
    source_components = [_component_count(item.geometry) for item in members]
    union_components = _component_count(union_geometry)
    source_widths = [_effective_width(item.geometry) for item in members]
    union_width = _effective_width(union_geometry)
    width_inflation = union_width / max(1e-9, max(source_widths))

    union_axis = _principal_axis(union_geometry)
    axis_drifts = []
    for item in members:
        source_axis = _principal_axis(item.geometry)
        dot = float(
            np.clip(abs(np.dot(union_axis, source_axis)), 0.0, 1.0)
        )
        axis_drifts.append(float(math.degrees(math.acos(dot))))
    max_axis_drift = max(axis_drifts) if axis_drifts else 0.0

    source_endpoints = []
    source_branches = []
    if class_name == "awn":
        for item in members:
            endpoints, branches = _skeleton_topology(item.geometry)
            source_endpoints.append(endpoints)
            source_branches.append(branches)
        union_endpoints, union_branches = _skeleton_topology(union_geometry)
    else:
        union_endpoints = 0
        union_branches = 0

    area_inflation = union_geometry.area / max(
        1e-9, max(item.geometry.area for item in members)
    )
    reasons: list[str] = []
    if union_geometry.is_empty or not union_geometry.is_valid:
        reasons.append("invalid_union_geometry")

    if class_name == "awn":
        if union_components > config.awn_component_count_max:
            reasons.append("too_many_components")
        if width_inflation > config.awn_width_inflation_max:
            reasons.append("width_inflation")
        if max_axis_drift > config.awn_axis_drift_max_deg:
            reasons.append("axis_drift")
        allowed_branch_excess = (
            config.awn_branchpoint_excess_max + max(0, len(members) - 2)
        )
        if union_branches > max(source_branches or [0]) + allowed_branch_excess:
            reasons.append("branch_explosion")
        if union_endpoints > max(source_endpoints or [0]) + config.awn_endpoint_excess_max:
            reasons.append("endpoint_explosion")
    else:
        if union_components > config.spikelet_component_count_max:
            reasons.append("too_many_components")
        if area_inflation > config.spikelet_area_inflation_max:
            reasons.append("area_inflation")

    diagnostics = {
        "fusion_accepted": not reasons,
        "reasons": reasons,
        "source_count": len(members),
        "source_component_counts": source_components,
        "union_component_count": union_components,
        "source_widths": source_widths,
        "union_width": union_width,
        "width_inflation": width_inflation,
        "max_axis_drift_deg": max_axis_drift,
        "area_inflation": area_inflation,
        "union_endpoints": union_endpoints,
        "union_branchpoints": union_branches,
        "allowed_branchpoint_excess": (
            config.awn_branchpoint_excess_max + max(0, len(members) - 2)
            if class_name == "awn"
            else 0
        ),
        "source_endpoints": source_endpoints,
        "source_branchpoints": source_branches,
        "source_tiles": sorted(
            {item.source_tile_id for item in members}
        ),
    }
    return not reasons, diagnostics


def _can_union_components(
    left_members: set[str],
    right_members: set[str],
    evidence_by_id: Mapping[str, DetectionEvidence],
    decisions_by_pair: Mapping[frozenset[str], PairDecision],
) -> bool:
    left_by_tile: dict[str, list[str]] = {}
    right_by_tile: dict[str, list[str]] = {}
    for evidence_id in left_members:
        item = evidence_by_id[evidence_id]
        left_by_tile.setdefault(item.source_tile_id, []).append(evidence_id)
    for evidence_id in right_members:
        item = evidence_by_id[evidence_id]
        right_by_tile.setdefault(item.source_tile_id, []).append(evidence_id)

    # Cross-tile non-duplicate pair decisions are not hard cannot-links.
    # Partial observations of one long object can be non-overlapping with each
    # other while both are strongly linked through an intermediate tile.
    # Preserve those pair decisions for audit, but let the strong-edge graph
    # form the candidate component; fusion_sanity() remains the geometry veto.
    #
    # Same-tile reuse is stricter: if the model emitted two observations in
    # one tile, they may coexist unless that exact pair is a strong duplicate.
    for tile_id in set(left_by_tile) & set(right_by_tile):
        for left_id in left_by_tile[tile_id]:
            for right_id in right_by_tile[tile_id]:
                decision = decisions_by_pair.get(
                    frozenset((left_id, right_id))
                )
                if (
                    decision is None
                    or decision.status
                    is not PairDecisionStatus.STRONG_DUPLICATE
                ):
                    return False
    return True


def _restricted_strong_groups(
    member_ids: Sequence[str],
    *,
    evidence_by_id: Mapping[str, DetectionEvidence],
    decisions: Sequence[PairDecision],
    decisions_by_pair: Mapping[frozenset[str], PairDecision],
) -> list[list[str]]:
    """Rebuild strong-edge groups inside a restricted evidence subset.

    Component-split evidence may enter one global strong component through
    cross-tile links even when an extra disconnected mask island should not
    poison the primary component. When a mixed-component fusion fails, this
    helper retries the already-observed strong graph within the primary and
    extra-component subsets independently. No pair decision is changed and no
    evidence is discarded.
    """

    selected = set(member_ids)
    if not selected:
        return []

    parent = {key: key for key in selected}
    members = {key: {key} for key in selected}

    def root(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    for decision in sorted(
        (
            item
            for item in decisions
            if item.status is PairDecisionStatus.STRONG_DUPLICATE
            and str(item.left_evidence_id) in selected
            and str(item.right_evidence_id) in selected
        ),
        key=lambda item: (item.strength, item.pair_id),
        reverse=True,
    ):
        left_root = root(str(decision.left_evidence_id))
        right_root = root(str(decision.right_evidence_id))
        if left_root == right_root:
            continue
        if not _can_union_components(
            members[left_root],
            members[right_root],
            evidence_by_id,
            decisions_by_pair,
        ):
            continue
        parent[right_root] = left_root
        members[left_root] |= members[right_root]
        del members[right_root]

    groups: dict[str, list[str]] = {}
    for evidence_id in selected:
        groups.setdefault(root(evidence_id), []).append(evidence_id)
    return sorted(
        (sorted(values) for values in groups.values()),
        key=lambda values: values[0],
    )


@reconciliation_computation_cache()
def reconcile_detection_evidence(
    evidence: Sequence[DetectionEvidence],
    *,
    config: ReconciliationConfig | None = None,
) -> ReconciliationResult:
    evidence = tuple(evidence)
    if not evidence:
        raise ValueError("reconciliation requires at least one DetectionEvidence")
    config = config or ReconciliationConfig()

    page_ids = {item.page_id for item in evidence}
    snapshot_ids = {str(item.snapshot_id) for item in evidence}
    if len(page_ids) != 1 or len(snapshot_ids) != 1:
        raise ValueError("all evidence must share one page and snapshot")
    page_id = next(iter(page_ids))
    snapshot_id = evidence[0].snapshot_id

    evidence_by_id = {
        str(item.evidence_id): item
        for item in evidence
    }
    if len(evidence_by_id) != len(evidence):
        raise ValueError("evidence IDs must be unique")

    decisions = generate_pair_decisions(evidence, config=config)
    decisions_by_pair = {
        frozenset(
            (
                str(item.left_evidence_id),
                str(item.right_evidence_id),
            )
        ): item
        for item in decisions
    }

    parent = {key: key for key in evidence_by_id}
    members = {key: {key} for key in evidence_by_id}

    def root(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    blocked_pairs: list[str] = []
    for decision in sorted(
        (
            item
            for item in decisions
            if item.status is PairDecisionStatus.STRONG_DUPLICATE
        ),
        key=lambda item: (item.strength, item.pair_id),
        reverse=True,
    ):
        left_root = root(str(decision.left_evidence_id))
        right_root = root(str(decision.right_evidence_id))
        if left_root == right_root:
            continue
        if not _can_union_components(
            members[left_root],
            members[right_root],
            evidence_by_id,
            decisions_by_pair,
        ):
            blocked_pairs.append(decision.pair_id)
            continue
        parent[right_root] = left_root
        members[left_root] |= members[right_root]
        del members[right_root]

    groups: dict[str, list[str]] = {}
    for evidence_id in evidence_by_id:
        groups.setdefault(root(evidence_id), []).append(evidence_id)

    ambiguous_incident: set[str] = set()
    for decision in decisions:
        if decision.status is PairDecisionStatus.AMBIGUOUS:
            ambiguous_incident.add(str(decision.left_evidence_id))
            ambiguous_incident.add(str(decision.right_evidence_id))
        if decision.pair_id in blocked_pairs:
            ambiguous_incident.add(str(decision.left_evidence_id))
            ambiguous_incident.add(str(decision.right_evidence_id))

    hypotheses: list[InstanceHypothesis] = []
    diagnostics: dict[str, Mapping[str, Any]] = {}

    def emit_hypothesis(
        member_ids: Sequence[str],
        *,
        component_salvage_partition: str | None = None,
        component_salvage_parent_ids: Sequence[str] = (),
        component_salvage_parent_reasons: Sequence[str] = (),
    ) -> None:
        ordered_member_ids = sorted(member_ids)
        cluster = [evidence_by_id[value] for value in ordered_member_ids]
        geometries = [item.geometry for item in cluster]
        fusion_accepted = False
        fusion_diagnostics: dict[str, Any] = {
            "fusion_accepted": False,
            "reasons": [],
            "source_count": len(cluster),
            "source_tiles": sorted(
                {item.source_tile_id for item in cluster}
            ),
        }

        if len(cluster) == 1:
            geometry = cluster[0].geometry
            status = (
                HypothesisStatus.AMBIGUOUS
                if ordered_member_ids[0] in ambiguous_incident
                else HypothesisStatus.SINGLETON
            )
            if status is HypothesisStatus.AMBIGUOUS:
                fusion_diagnostics["reasons"] = [
                    "unresolved_ambiguous_pair"
                ]
        else:
            union_geometry = unary_union(geometries)
            fusion_accepted, fusion_diagnostics = fusion_sanity(
                cluster,
                union_geometry,
                config=config,
            )
            if fusion_accepted:
                geometry = union_geometry
                status = HypothesisStatus.FUSED
            else:
                geometry = GeometryCollection(tuple(geometries))
                status = HypothesisStatus.AMBIGUOUS

        salvage_payload: dict[str, Any] | None = None
        if component_salvage_partition is not None:
            salvage_payload = {
                "partition": component_salvage_partition,
                "parent_evidence_ids": sorted(
                    str(value) for value in component_salvage_parent_ids
                ),
                "parent_reasons": list(component_salvage_parent_reasons),
            }
            fusion_diagnostics = {
                **fusion_diagnostics,
                "component_salvage": salvage_payload,
            }

        draft = InstanceHypothesis.create(
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_id=cluster[0].class_id,
            class_name=cluster[0].class_name,
            evidence_ids=tuple(
                item.evidence_id for item in cluster
            ),
            geometry=geometry,
            status=status,
        )
        provenance = OperationProvenance(
            operation="reconcile_detection_evidence",
            implementation=RECONCILIATION_IMPLEMENTATION,
            input_ids=tuple(ordered_member_ids),
            output_id=str(draft.hypothesis_id),
            status=status.value,
            parameters={
                "fusion_strategy": (
                    "union_of_complementary_geometry"
                    if fusion_accepted
                    else "preserve_unfused_geometry"
                ),
                "component_salvage_partition": (
                    component_salvage_partition
                ),
                "config_sha256": canonical_json_sha256(
                    config.to_dict()
                ),
            },
            evidence={
                "fusion_sanity": fusion_diagnostics,
                "ambiguous_incident": any(
                    value in ambiguous_incident
                    for value in ordered_member_ids
                ),
                "component_salvage": salvage_payload,
            },
        )
        hypothesis = InstanceHypothesis.create(
            snapshot_id=snapshot_id,
            page_id=page_id,
            class_id=cluster[0].class_id,
            class_name=cluster[0].class_name,
            evidence_ids=tuple(
                item.evidence_id for item in cluster
            ),
            geometry=geometry,
            status=status,
            provenance=(provenance,),
        )
        hypotheses.append(hypothesis)
        diagnostics[str(hypothesis.hypothesis_id)] = {
            **fusion_diagnostics,
            "status": status.value,
            "evidence_ids": ordered_member_ids,
        }

    for member_ids in sorted(
        (sorted(value) for value in groups.values()),
        key=lambda values: values[0],
    ):
        cluster = [evidence_by_id[value] for value in member_ids]
        component_zero_ids = [
            value
            for value in member_ids
            if evidence_by_id[value].source_component_index == 0
        ]
        extra_component_ids = [
            value
            for value in member_ids
            if evidence_by_id[value].source_component_index > 0
        ]

        should_salvage = False
        parent_reasons: list[str] = []
        if (
            len(cluster) > 1
            and component_zero_ids
            and extra_component_ids
        ):
            union_geometry = unary_union(
                [item.geometry for item in cluster]
            )
            fusion_accepted, full_diagnostics = fusion_sanity(
                cluster,
                union_geometry,
                config=config,
            )
            should_salvage = not fusion_accepted
            parent_reasons = list(full_diagnostics.get("reasons") or [])

        if should_salvage:
            primary_groups = _restricted_strong_groups(
                component_zero_ids,
                evidence_by_id=evidence_by_id,
                decisions=decisions,
                decisions_by_pair=decisions_by_pair,
            )
            extra_groups = _restricted_strong_groups(
                extra_component_ids,
                evidence_by_id=evidence_by_id,
                decisions=decisions,
                decisions_by_pair=decisions_by_pair,
            )
            for subgroup in primary_groups:
                emit_hypothesis(
                    subgroup,
                    component_salvage_partition="primary_component",
                    component_salvage_parent_ids=member_ids,
                    component_salvage_parent_reasons=parent_reasons,
                )
            for subgroup in extra_groups:
                emit_hypothesis(
                    subgroup,
                    component_salvage_partition="extra_component",
                    component_salvage_parent_ids=member_ids,
                    component_salvage_parent_reasons=parent_reasons,
                )
            continue

        emit_hypothesis(member_ids)

    config_payload = config.to_dict()
    return ReconciliationResult(
        page_id=page_id,
        snapshot_id=snapshot_id,
        source_evidence_ids=tuple(
            item.evidence_id
            for item in sorted(
                evidence, key=lambda item: str(item.evidence_id)
            )
        ),
        pair_decisions=decisions,
        hypotheses=tuple(
            sorted(
                hypotheses,
                key=lambda item: str(item.hypothesis_id),
            )
        ),
        hypothesis_diagnostics=diagnostics,
        config_payload=config_payload,
        config_sha256=canonical_json_sha256(config_payload),
        blocked_strong_pair_ids=tuple(blocked_pairs),
    )


__all__ = [
    "RECONCILIATION_FILE_SCHEMA",
    "RECONCILIATION_IMPLEMENTATION",
    "ClassReconciliationThresholds",
    "PairDecision",
    "PairDecisionStatus",
    "PairFeatures",
    "ReconciliationConfig",
    "ReconciliationResult",
    "classify_pair",
    "fusion_sanity",
    "generate_pair_decisions",
    "pair_features",
    "reconcile_detection_evidence",
    "reconciliation_computation_cache",
]
