"""Configuration for the maintained Unified Growth awn reconstruction algorithm."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .crossing import CrossingPolicy

from awnphen.phenotyping.physical.trajectory import (
    CONTINUATION_MAX_ANGLE_DEG,
    CONTINUATION_PCA_SPANS_MM,
    DISTAL_TANGENT_FIT_SPAN_MM,
    DISTAL_TANGENT_TRIM_MM,
)


@dataclass(frozen=True, slots=True)
class UnifiedGrowthConfig:
    """Scientific policy for Unified Growth v1."""

    crossing_guard_enabled: bool = True
    crossing_policy: CrossingPolicy = CrossingPolicy()

    primary_confidence: float = 0.50
    compaction_overlap: float = 0.92
    max_provisional_seeds_per_spikelet: int = 4
    direct_root_max_mm: float = 2.8
    project_root_ray_mm: float = 4.5
    project_root_max_distance_mm: float = 1.2

    # Orientation is anchored by spikelet geometry.  Awn evidence is allowed to
    # resolve only the remaining page-polarity ambiguity when it is itself
    # aligned with a nearby spikelet.  Seed paths then get a local axis gate.
    orientation_vote_max_axis_angle_deg: float = 45.0
    orientation_vote_max_distance_mm: float = 5.0
    seed_max_axis_deviation_deg: float = 75.0

    growth_max_hops: int = 10
    growth_min_extension_mm: float = 0.35
    growth_max_distance_mm: float = 2.8
    growth_max_local_angle_deg: float = 55.0
    growth_max_trend_angle_deg: float = 70.0
    growth_max_internal_turn_deg: float = 90.0
    growth_max_multiscale_angle_deg: float = CONTINUATION_MAX_ANGLE_DEG

    join_window_mm: float = 4.0
    join_turn_span_mm: float = 1.5
    join_max_local_turn_deg: float = 22.0
    join_max_excess_turn_deg: float = 8.0

    ownership_share_rel_margin: float = 0.05
    trajectory_span_mm: float = 5.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["multiscale_spans_mm"] = list(CONTINUATION_PCA_SPANS_MM)
        payload["distal_tangent_trim_mm"] = DISTAL_TANGENT_TRIM_MM
        payload["distal_tangent_fit_span_mm"] = DISTAL_TANGENT_FIT_SPAN_MM
        return payload


DEFAULT_UNIFIED_GROWTH_CONFIG = UnifiedGrowthConfig()

__all__ = ["UnifiedGrowthConfig", "DEFAULT_UNIFIED_GROWTH_CONFIG"]
