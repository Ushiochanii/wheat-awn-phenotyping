"""Measurement-only centerline simplification.

The physical centerline is preserved as provenance.  This module derives a
measurement path that removes sub-pixel-grid staircase detail before physical
length conversion.
"""

from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry import LineString

DEFAULT_MEASUREMENT_SIMPLIFY_TOLERANCE_PX = 1.0


def simplify_measurement_path(
    path: Sequence[Sequence[float]],
    *,
    tolerance_px: float = DEFAULT_MEASUREMENT_SIMPLIFY_TOLERANCE_PX,
) -> tuple[tuple[float, float], ...]:
    """Douglas-Peucker simplify while preserving endpoints.

    The simplification is measurement-only: callers should retain the input
    path as the physical/raw centerline for provenance and visual audit.
    """
    points = tuple(
        (float(point[0]), float(point[1]))
        for point in path
    )
    if len(points) < 3 or tolerance_px <= 0.0:
        return points

    simplified = LineString(points).simplify(
        float(tolerance_px),
        preserve_topology=False,
    )
    result = tuple(
        (float(x), float(y))
        for x, y in simplified.coords
    )
    if len(result) < 2:
        return points

    # GEOS/DP preserves line endpoints, but keep this invariant explicit.
    if result[0] != points[0] or result[-1] != points[-1]:
        return (
            points[0],
            *result[1:-1],
            points[-1],
        )
    return result


__all__ = [
    "DEFAULT_MEASUREMENT_SIMPLIFY_TOLERANCE_PX",
    "simplify_measurement_path",
]
