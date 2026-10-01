"""Shared page/spikelet orientation utilities for physical phenotyping.

The page axis is defined from spikelet geometry.  Polarity can then be resolved
with a policy chosen by the caller.  Unified Growth uses the spikelet-anchored
policy so arbitrary awn-like clutter cannot dominate the up/down decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from shapely.ops import transform as shapely_transform


@dataclass(frozen=True)
class ScaleContext:
    x_period_px_5mm: float
    y_period_px_5mm: float
    adequate: bool | None
    source: str = "existing_grid_calibration_v2"

    @property
    def x_mm_per_px(self) -> float:
        return 5.0 / self.x_period_px_5mm

    @property
    def y_mm_per_px(self) -> float:
        return 5.0 / self.y_period_px_5mm


@dataclass(frozen=True)
class OrientationTransform:
    scale: ScaleContext
    rotation_rad: float
    polarity_flipped: bool
    axis_concentration: float
    polarity_confidence: float

    def raw_px_to_canonical_mm(
        self, point: tuple[float, float]
    ) -> tuple[float, float]:
        x = float(point[0]) * self.scale.x_mm_per_px
        y = float(point[1]) * self.scale.y_mm_per_px
        c, s = math.cos(self.rotation_rad), math.sin(self.rotation_rad)
        return (c * x - s * y, s * x + c * y)

    def canonical_mm_to_raw_px(
        self, point: tuple[float, float]
    ) -> tuple[float, float]:
        c, s = math.cos(self.rotation_rad), math.sin(self.rotation_rad)
        x_mm = c * float(point[0]) + s * float(point[1])
        y_mm = -s * float(point[0]) + c * float(point[1])
        return (
            x_mm / self.scale.x_mm_per_px,
            y_mm / self.scale.y_mm_per_px,
        )

    def geometry_to_canonical_mm(self, geometry):
        def fn(x, y, z=None):
            try:
                return tuple(
                    zip(
                        *(
                            self.raw_px_to_canonical_mm((float(a), float(b)))
                            for a, b in zip(x, y)
                        )
                    )
                )
            except TypeError:
                xx, yy = self.raw_px_to_canonical_mm((float(x), float(y)))
                return (xx, yy)

        return shapely_transform(fn, geometry)


def load_scale(calibration_by_page, page_id: str) -> ScaleContext:
    item = calibration_by_page[page_id]
    x, y = float(item["x"]), float(item["y"])
    if x <= 0 or y <= 0:
        raise ValueError(f"invalid calibration for {page_id}")
    return ScaleContext(
        x_period_px_5mm=x,
        y_period_px_5mm=y,
        adequate=None if item.get("adequate") is None else bool(item.get("adequate")),
    )


def major_axis_angle_rad(geometry, scale: ScaleContext) -> float:
    def to_mm(x, y, z=None):
        try:
            xs = [float(v) * scale.x_mm_per_px for v in x]
            ys = [float(v) * scale.y_mm_per_px for v in y]
            return (xs, ys)
        except TypeError:
            return (
                float(x) * scale.x_mm_per_px,
                float(y) * scale.y_mm_per_px,
            )

    g = shapely_transform(to_mm, geometry)
    rect = g.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    best = None
    for a, b in zip(coords, coords[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if best is None or length > best[0]:
            best = (length, math.atan2(dy, dx))
    if best is None or best[0] <= 0:
        raise ValueError("degenerate spikelet geometry")
    return best[1] % math.pi


def major_axis_vector(geometry) -> tuple[float, float]:
    rect = geometry.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)
    best = None
    for a, b in zip(coords, coords[1:]):
        dx, dy = float(b[0] - a[0]), float(b[1] - a[1])
        length = math.hypot(dx, dy)
        if best is None or length > best[0]:
            best = (length, dx, dy)
    if best is None or best[0] <= 1e-9:
        raise ValueError("degenerate geometry axis")
    return (best[1] / best[0], best[2] / best[0])


def axis_angle_deg(
    first: tuple[float, float],
    second: tuple[float, float],
    *,
    directed: bool = False,
) -> float:
    dot = float(first[0] * second[0] + first[1] * second[1])
    if not directed:
        dot = abs(dot)
    dot = max(-1.0, min(1.0, dot))
    return float(math.degrees(math.acos(dot)))


def spikelet_outward_axis(canonical_geometry) -> tuple[float, float]:
    """Return the local spikelet major axis oriented toward canonical UP."""
    x, y = major_axis_vector(canonical_geometry)
    if y > 0.0 or (abs(y) <= 1e-12 and x < 0.0):
        x, y = -x, -y
    return (x, y)


def initial_path_direction(
    canonical_path,
    *,
    span_mm: float = 2.0,
) -> tuple[float, float] | None:
    if len(canonical_path) < 2:
        return None
    start = canonical_path[0]
    distance = 0.0
    for index in range(1, len(canonical_path)):
        previous = canonical_path[index - 1]
        current = canonical_path[index]
        distance += math.hypot(
            current[0] - previous[0],
            current[1] - previous[1],
        )
        if distance >= span_mm or index == len(canonical_path) - 1:
            dx = float(current[0] - start[0])
            dy = float(current[1] - start[1])
            norm = math.hypot(dx, dy)
            if norm <= 1e-9:
                return None
            return (dx / norm, dy / norm)
    return None


def seed_axis_deviation_deg(canonical_path, spikelet_geometry) -> float | None:
    direction = initial_path_direction(canonical_path)
    if direction is None:
        return None
    outward = spikelet_outward_axis(spikelet_geometry)
    return axis_angle_deg(direction, outward, directed=True)


def _confidence(hypothesis, evidence_by_id) -> float:
    values = [
        float(evidence_by_id[str(eid)].confidence)
        for eid in hypothesis.evidence_ids
        if str(eid) in evidence_by_id
    ]
    if not values:
        raise ValueError(
            f"hypothesis has no evidence confidence: {hypothesis.hypothesis_id}"
        )
    return max(values)


def _usable_spikelets(hypotheses, evidence_by_id, primary_confidence):
    return [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.class_name == "spikelet"
        and hypothesis.status.value != "ambiguous"
        and _confidence(hypothesis, evidence_by_id) >= primary_confidence
    ]


def build_canonical_spikelets(
    hypotheses,
    evidence_by_id,
    transform: OrientationTransform,
    *,
    primary_confidence: float,
) -> list[dict[str, object]]:
    """Project trusted spikelets into the shared canonical orientation frame."""
    rows = []
    for hypothesis in _usable_spikelets(
        hypotheses,
        evidence_by_id,
        primary_confidence,
    ):
        geometry = transform.geometry_to_canonical_mm(hypothesis.geometry)
        rows.append(
            {
                "id": str(hypothesis.hypothesis_id),
                "geometry": hypothesis.geometry,
                "canonical_geometry": geometry,
                "centroid_y": float(geometry.centroid.y),
                "max_confidence": _confidence(hypothesis, evidence_by_id),
            }
        )
    return rows


def _axis_frame(usable_spikelets, scale):
    if not usable_spikelets:
        raise ValueError("orientation requires at least one primary spikelet")
    angles = [major_axis_angle_rad(item.geometry, scale) for item in usable_spikelets]
    c2 = sum(math.cos(2.0 * angle) for angle in angles)
    s2 = sum(math.sin(2.0 * angle) for angle in angles)
    axis = 0.5 * math.atan2(s2, c2)
    # With one spikelet there is no population agreement to measure.  Its long
    # axis is still sufficient to establish a usable frame, but concentration
    # must not pretend that a one-sample "consensus" is high confidence.
    concentration = (
        0.0
        if len(angles) == 1
        else math.hypot(c2, s2) / len(angles)
    )
    rotation = (math.pi / 2.0) - axis
    return rotation, concentration


def estimate_legacy_orientation(
    hypotheses,
    evidence_by_id,
    scale: ScaleContext,
    *,
    primary_confidence: float,
) -> OrientationTransform:
    """Historical centroid-vote polarity retained for reproducibility."""
    spikelets = _usable_spikelets(
        hypotheses, evidence_by_id, primary_confidence
    )
    rotation, concentration = _axis_frame(spikelets, scale)
    provisional = OrientationTransform(
        scale=scale,
        rotation_rad=rotation,
        polarity_flipped=False,
        axis_concentration=concentration,
        polarity_confidence=0.0,
    )
    spikelet_centers = [
        provisional.raw_px_to_canonical_mm(
            (item.geometry.centroid.x, item.geometry.centroid.y)
        )
        for item in spikelets
    ]
    votes = []
    for hypothesis in hypotheses:
        if hypothesis.class_name != "awn" or hypothesis.status.value == "ambiguous":
            continue
        if _confidence(hypothesis, evidence_by_id) < primary_confidence:
            continue
        center = provisional.raw_px_to_canonical_mm(
            (hypothesis.geometry.centroid.x, hypothesis.geometry.centroid.y)
        )
        nearest = min(
            spikelet_centers,
            key=lambda point: math.hypot(
                center[0] - point[0],
                center[1] - point[1],
            ),
        )
        dy = center[1] - nearest[1]
        if abs(dy) > 1e-6:
            votes.append(-1 if dy < 0 else 1)

    flip = bool(votes and statistics.median(votes) > 0)
    if flip:
        rotation += math.pi
    confidence = abs(sum(votes)) / len(votes) if votes else 0.0
    return OrientationTransform(
        scale=scale,
        rotation_rad=rotation,
        polarity_flipped=flip,
        axis_concentration=concentration,
        polarity_confidence=confidence,
    )


def estimate_spikelet_anchored_orientation(
    hypotheses,
    evidence_by_id,
    scale: ScaleContext,
    *,
    primary_confidence: float,
    vote_max_axis_angle_deg: float,
    vote_max_distance_mm: float,
) -> tuple[OrientationTransform, dict[str, object]]:
    """Resolve polarity using at most one axis-compatible awn vote per spikelet.

    Page rotation is estimated from spikelets only.  Awn evidence may resolve
    only the remaining 180-degree polarity ambiguity, and only when it is close
    to a spikelet and its own long axis is compatible with that spikelet's long
    axis.  This prevents repeated transverse clutter from dominating polarity.
    """
    spikelets = _usable_spikelets(
        hypotheses, evidence_by_id, primary_confidence
    )
    rotation, concentration = _axis_frame(spikelets, scale)
    if len(spikelets) == 1:
        # A single spikelet can define the page axis but cannot establish a
        # population-backed up/down polarity. Treat that uncertainty as a
        # normal degraded case: keep the default polarity and continue.
        transform = OrientationTransform(
            scale=scale,
            rotation_rad=rotation,
            polarity_flipped=False,
            axis_concentration=concentration,
            polarity_confidence=0.0,
        )
        return transform, {
            "policy": "single_spikelet_default_polarity",
            "spikelet_axis_vote_count": 0,
            "eligible_spikelet_awn_pairs": 0,
            "vote_balance": 0,
            "vote_max_axis_angle_deg": float(vote_max_axis_angle_deg),
            "vote_max_distance_mm": float(vote_max_distance_mm),
            "primary_spikelet_count": 1,
            "orientation_degraded": True,
        }
    provisional = OrientationTransform(
        scale=scale,
        rotation_rad=rotation,
        polarity_flipped=False,
        axis_concentration=concentration,
        polarity_confidence=0.0,
    )
    canonical_spikelets = [
        {
            "hypothesis": item,
            "geometry": provisional.geometry_to_canonical_mm(item.geometry),
        }
        for item in spikelets
    ]

    awns = []
    for hypothesis in hypotheses:
        if hypothesis.class_name != "awn" or hypothesis.status.value == "ambiguous":
            continue
        confidence = _confidence(hypothesis, evidence_by_id)
        if confidence < primary_confidence:
            continue
        geometry = provisional.geometry_to_canonical_mm(hypothesis.geometry)
        try:
            axis = major_axis_vector(geometry)
        except ValueError:
            continue
        awns.append(
            {
                "hypothesis": hypothesis,
                "geometry": geometry,
                "axis": axis,
                "confidence": confidence,
            }
        )

    votes = []
    eligible_pairs = 0
    for spikelet in canonical_spikelets:
        geometry = spikelet["geometry"]
        try:
            spikelet_axis = major_axis_vector(geometry)
        except ValueError:
            continue
        candidates = []
        for awn in awns:
            distance = float(geometry.distance(awn["geometry"]))
            if distance > vote_max_distance_mm:
                continue
            angle = axis_angle_deg(spikelet_axis, awn["axis"])
            if angle > vote_max_axis_angle_deg:
                continue
            dy = float(awn["geometry"].centroid.y - geometry.centroid.y)
            if abs(dy) <= 1e-6:
                continue
            eligible_pairs += 1
            candidates.append(
                (
                    angle,
                    distance,
                    -float(awn["confidence"]),
                    -1 if dy < 0 else 1,
                )
            )
        if candidates:
            candidates.sort()
            votes.append(int(candidates[0][3]))

    source = "spikelet_axis_anchored"
    if votes:
        flip = statistics.median(votes) > 0
        confidence = abs(sum(votes)) / len(votes)
    else:
        legacy = estimate_legacy_orientation(
            hypotheses,
            evidence_by_id,
            scale,
            primary_confidence=primary_confidence,
        )
        flip = bool(legacy.polarity_flipped)
        confidence = float(legacy.polarity_confidence)
        source = "legacy_centroid_fallback"

    if flip:
        rotation += math.pi
    transform = OrientationTransform(
        scale=scale,
        rotation_rad=rotation,
        polarity_flipped=bool(flip),
        axis_concentration=concentration,
        polarity_confidence=confidence,
    )
    return transform, {
        "policy": source,
        "spikelet_axis_vote_count": len(votes),
        "eligible_spikelet_awn_pairs": int(eligible_pairs),
        "vote_balance": int(sum(votes)),
        "vote_max_axis_angle_deg": float(vote_max_axis_angle_deg),
        "vote_max_distance_mm": float(vote_max_distance_mm),
        "primary_spikelet_count": len(spikelets),
        "orientation_degraded": False,
    }


__all__ = [
    "ScaleContext",
    "OrientationTransform",
    "load_scale",
    "major_axis_angle_rad",
    "major_axis_vector",
    "axis_angle_deg",
    "spikelet_outward_axis",
    "initial_path_direction",
    "seed_axis_deviation_deg",
    "build_canonical_spikelets",
    "estimate_legacy_orientation",
    "estimate_spikelet_anchored_orientation",
]
