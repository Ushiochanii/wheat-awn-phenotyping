"""Local trajectory geometry used by Unified Growth v1."""
from __future__ import annotations

import math

from shapely.geometry import LineString
from shapely.ops import nearest_points

from awnphen.phenotyping.physical.trajectory import max_local_turn
from .config import DEFAULT_UNIFIED_GROWTH_CONFIG

_CONFIG = DEFAULT_UNIFIED_GROWTH_CONFIG
TRAJECTORY_SPAN_MM = _CONFIG.trajectory_span_mm
JOIN_WINDOW_MM = _CONFIG.join_window_mm
JOIN_TURN_SPAN_MM = _CONFIG.join_turn_span_mm
PROJECT_ROOT_RAY_MM = _CONFIG.project_root_ray_mm
PROJECT_ROOT_MAX_DISTANCE_MM = _CONFIG.project_root_max_distance_mm


def _first_direction(path, span_mm=2.0):
    if len(path) < 2:
        return None
    distance = 0.0
    start = path[0]
    for i in range(1, len(path)):
        step = math.hypot(path[i][0] - path[i-1][0], path[i][1] - path[i-1][1])
        distance += step
        if distance >= span_mm or i == len(path) - 1:
            return (path[i][0] - start[0], path[i][1] - start[1])
    return None


def _recent_trajectory(path, span_mm=TRAJECTORY_SPAN_MM):
    if len(path) < 2:
        return None
    tip = path[-1]
    distance = 0.0
    i = len(path) - 1
    while i > 0 and distance < span_mm:
        distance += math.hypot(
            path[i][0] - path[i-1][0],
            path[i][1] - path[i-1][1],
        )
        i -= 1
    return (tip[0] - path[i][0], tip[1] - path[i][1])


def _tail_window(path, span_mm=JOIN_WINDOW_MM):
    if len(path) < 2:
        return list(path)
    out = [path[-1]]
    distance = 0.0
    i = len(path) - 1
    while i > 0 and distance < span_mm:
        distance += math.hypot(
            path[i][0] - path[i-1][0],
            path[i][1] - path[i-1][1],
        )
        i -= 1
        out.append(path[i])
    return list(reversed(out))


def _head_window(path, span_mm=JOIN_WINDOW_MM):
    if len(path) < 2:
        return list(path)
    out = [path[0]]
    distance = 0.0
    i = 0
    while i + 1 < len(path) and distance < span_mm:
        distance += math.hypot(
            path[i+1][0] - path[i][0],
            path[i+1][1] - path[i][1],
        )
        i += 1
        out.append(path[i])
    return out


def _join_turn_metrics(current_can, suffix_can):
    current_tail = _tail_window(current_can)
    support_head = _head_window(suffix_can)
    merged_local = current_tail + support_head
    current_turn = max_local_turn(current_tail, span=JOIN_TURN_SPAN_MM)
    support_turn = max_local_turn(support_head, span=JOIN_TURN_SPAN_MM)
    merged_turn = max_local_turn(merged_local, span=JOIN_TURN_SPAN_MM)
    intrinsic_turn = max(current_turn, support_turn)
    return {
        "join_local_turn_deg": float(merged_turn),
        "join_intrinsic_turn_deg": float(intrinsic_turn),
        "join_excess_turn_deg": float(max(0.0, merged_turn - intrinsic_turn)),
    }


def _projected_root_match(can_path, spikelet):
    root = can_path[0]
    direction = _first_direction(can_path)
    if direction is None:
        return None
    norm = math.hypot(*direction)
    if norm < 1e-9:
        return None

    # Seed path points from root toward distal tip. Back-project toward the spikelet.
    bx = -direction[0] / norm
    by = -direction[1] / norm
    projected = (
        root[0] + bx * PROJECT_ROOT_RAY_MM,
        root[1] + by * PROJECT_ROOT_RAY_MM,
    )
    ray = LineString([root, projected])
    geometry = spikelet["canonical_geometry"]
    distance = float(ray.distance(geometry))
    closest_spikelet, _ = nearest_points(geometry, ray)
    upper_half = float(closest_spikelet.y) <= float(spikelet["centroid_y"])
    if not upper_half or distance > PROJECT_ROOT_MAX_DISTANCE_MM:
        return None
    return distance

__all__ = ["_recent_trajectory", "_join_turn_metrics", "_projected_root_match"]
