"""Shared geometric primitives for physical awn trajectories.

This module contains deterministic geometry/skeleton operations used by the
maintained Unified Growth route.  It deliberately contains no reconstruction,
completion, ownership, or biological-selection policy so current algorithms do
not need to import historical pipeline modules just to reuse geometry helpers.
"""
from __future__ import annotations

import math
import statistics

import numpy as np

from awnphen.core.geometry.instances import parts
from awnphen.core.geometry.skeleton import (
    NEIGHBORS,
    largest_skeleton_component,
    rasterize,
    skeleton_diameter,
)


# Historical values promoted as shared physical-geometry defaults.  Keeping the
# numeric values unchanged preserves existing scientific behavior.
CONTINUATION_MIN_EXTENSION_MM = 2.0
CONTINUATION_MAX_SKELETON_DISTANCE_MM = 0.8
CONTINUATION_MAX_ANGLE_DEG = 20.0
CONTINUATION_TANGENT_SPAN_MM = 1.5
CONTINUATION_PCA_SPANS_MM = (1.5, 2.0, 3.0)
DISTAL_TANGENT_TRIM_MM = 0.5
DISTAL_TANGENT_FIT_SPAN_MM = 3.0


def angle_deg(left, right) -> float | None:
    ln = math.hypot(*left)
    rn = math.hypot(*right)
    if ln <= 1e-9 or rn <= 1e-9:
        return None
    cosine = max(
        -1.0,
        min(
            1.0,
            (left[0] * right[0] + left[1] * right[1]) / (ln * rn),
        ),
    )
    return math.degrees(math.acos(cosine))


def chunk_vectors(path, span: float = 2.0):
    out = []
    indices = []
    index = 0
    while index < len(path) - 1:
        distance = 0.0
        distal = index
        while distal < len(path) - 1 and distance < span:
            distance += math.hypot(
                path[distal + 1][0] - path[distal][0],
                path[distal + 1][1] - path[distal][1],
            )
            distal += 1
        if distal == index:
            break
        out.append(
            (
                path[distal][0] - path[index][0],
                path[distal][1] - path[index][1],
            )
        )
        indices.append((index, distal))
        index = distal
    return out, indices


def path_length(path) -> float:
    return float(
        sum(
            math.hypot(b[0] - a[0], b[1] - a[1])
            for a, b in zip(path, path[1:])
        )
    )


def max_local_turn(path, *, span: float = 2.0) -> float:
    vectors, _ = chunk_vectors(path, span)
    turns = [angle_deg(a, b) for a, b in zip(vectors, vectors[1:])]
    return float(max((value for value in turns if value is not None), default=0.0))


def skeleton_features(geometry):
    """Return the branch/topology and diameter-path features of a mask geometry."""
    component_count = len(parts(geometry))
    mask, offset = rasterize(geometry)
    nodes = largest_skeleton_component(mask)
    if len(nodes) < 2:
        return {
            "component_count": component_count,
            "nodes": nodes,
            "offset": offset,
            "endpoint_count": 0,
            "branch_node_count": 0,
            "path": (),
            "length_px": 0.0,
            "diameter_node_fraction": 0.0,
        }
    degrees = {
        point: sum(
            (point[0] + dx, point[1] + dy) in nodes
            for dx, dy, _ in NEIGHBORS
        )
        for point in nodes
    }
    endpoints = [point for point, degree in degrees.items() if degree == 1]
    branch_nodes = [point for point, degree in degrees.items() if degree > 2]
    local_path, length_px = skeleton_diameter(nodes)
    raw_path = tuple(
        (float(x + offset[0]), float(y + offset[1]))
        for x, y in local_path
    )
    diameter_node_fraction = (
        float(len(set(local_path)) / len(nodes)) if nodes else 0.0
    )
    return {
        "component_count": component_count,
        "nodes": nodes,
        "offset": offset,
        "endpoint_count": len(endpoints),
        "branch_node_count": len(branch_nodes),
        "path": raw_path,
        "length_px": float(length_px),
        "diameter_node_fraction": diameter_node_fraction,
    }


def _point_from_end(path, distance_mm):
    if len(path) < 2:
        return None
    if distance_mm <= 0.0:
        return (float(path[-1][0]), float(path[-1][1]))
    remaining = float(distance_mm)
    for index in range(len(path) - 1, 0, -1):
        end = np.asarray(path[index], dtype=float)
        start = np.asarray(path[index - 1], dtype=float)
        segment = float(np.linalg.norm(end - start))
        if segment <= 1e-12:
            continue
        if remaining <= segment:
            point = end + (remaining / segment) * (start - end)
            return (float(point[0]), float(point[1]))
        remaining -= segment
    return (float(path[0][0]), float(path[0][1]))


def _trimmed_backward_window(path, *, trim_mm, span_mm):
    if len(path) < 2 or span_mm <= 0.0:
        return []
    near = _point_from_end(path, trim_mm)
    far = _point_from_end(path, trim_mm + span_mm)
    if near is None or far is None:
        return []

    distances_from_end = [0.0] * len(path)
    distance = 0.0
    for index in range(len(path) - 1, 0, -1):
        distance += math.hypot(
            path[index][0] - path[index - 1][0],
            path[index][1] - path[index - 1][1],
        )
        distances_from_end[index - 1] = distance

    middle = [
        (float(point[0]), float(point[1]))
        for point, distance in zip(path, distances_from_end)
        if trim_mm < distance < trim_mm + span_mm
    ]
    return [far, *reversed(middle), near]


def distal_tangent(
    path,
    *,
    trim_mm: float = DISTAL_TANGENT_TRIM_MM,
    span_mm: float = DISTAL_TANGENT_FIT_SPAN_MM,
):
    """Estimate distal direction from the stable pre-tip trajectory.

    The physical path itself is unchanged. Only the continuation direction is
    estimated after ignoring the final trim_mm segment and fitting the preceding
    span_mm window with PCA.
    """
    if len(path) < 2:
        return None
    window = _trimmed_backward_window(
        path,
        trim_mm=max(0.0, float(trim_mm)),
        span_mm=max(0.0, float(span_mm)),
    )
    fitted = _pca_direction(window)
    if fitted is not None:
        direction, _ = fitted
        return direction

    distance = 0.0
    index = len(path) - 1
    while index > 0 and distance < CONTINUATION_TANGENT_SPAN_MM:
        distance += math.hypot(
            path[index][0] - path[index - 1][0],
            path[index][1] - path[index - 1][1],
        )
        index -= 1
    return (
        path[-1][0] - path[index][0],
        path[-1][1] - path[index][1],
    )


def continuation_tangent(
    path,
    tip,
    *,
    span_mm: float = CONTINUATION_TANGENT_SPAN_MM,
):
    if len(path) < 2:
        return None, None
    index = min(
        range(len(path)),
        key=lambda i: math.hypot(
            path[i][0] - tip[0],
            path[i][1] - tip[1],
        ),
    )
    skeleton_distance = math.hypot(
        path[index][0] - tip[0],
        path[index][1] - tip[1],
    )
    distance = 0.0
    distal = index
    while distal < len(path) - 1 and distance < span_mm:
        distance += math.hypot(
            path[distal + 1][0] - path[distal][0],
            path[distal + 1][1] - path[distal][1],
        )
        distal += 1
    if distal == index:
        return None, skeleton_distance
    return (
        (
            path[distal][0] - path[index][0],
            path[distal][1] - path[index][1],
        ),
        skeleton_distance,
    )


def _local_window_backward(path, span_mm):
    if len(path) < 2:
        return []
    distance = 0.0
    index = len(path) - 1
    while index > 0 and distance < span_mm:
        distance += math.hypot(
            path[index][0] - path[index - 1][0],
            path[index][1] - path[index - 1][1],
        )
        index -= 1
    return path[index:]


def _local_window_forward(path, tip, span_mm):
    if len(path) < 2:
        return []
    index = min(
        range(len(path)),
        key=lambda i: math.hypot(
            path[i][0] - tip[0],
            path[i][1] - tip[1],
        ),
    )
    distance = 0.0
    distal = index
    while distal < len(path) - 1 and distance < span_mm:
        distance += math.hypot(
            path[distal + 1][0] - path[distal][0],
            path[distal + 1][1] - path[distal][1],
        )
        distal += 1
    return path[index : distal + 1]


def _pca_direction(points):
    if len(points) < 2:
        return None
    arr = np.asarray(points, dtype=float)
    centered = arr - arr.mean(axis=0)
    if float(np.linalg.norm(centered)) <= 1e-12:
        return None
    _, singular, vh = np.linalg.svd(centered, full_matrices=False)
    direction = vh[0]
    progression = arr[-1] - arr[0]
    if float(np.dot(direction, progression)) < 0:
        direction = -direction
    linearity = None
    if len(singular) >= 2:
        denom = float(np.sum(singular ** 2))
        if denom > 1e-12:
            linearity = float((singular[0] ** 2) / denom)
    return (float(direction[0]), float(direction[1])), linearity


def multiscale_continuation_angle(
    target_path,
    support_path,
    tip,
    *,
    spans_mm=CONTINUATION_PCA_SPANS_MM,
):
    diagnostics = []
    for span_mm in spans_mm:
        target_window = _local_window_backward(target_path, span_mm)
        support_window = _local_window_forward(support_path, tip, span_mm)
        target_fit = _pca_direction(target_window)
        support_fit = _pca_direction(support_window)
        if target_fit is None or support_fit is None:
            continue
        target_direction, target_linearity = target_fit
        support_direction, support_linearity = support_fit
        angle = angle_deg(target_direction, support_direction)
        if angle is None:
            continue
        diagnostics.append(
            {
                "span_mm": float(span_mm),
                "angle_deg": float(angle),
                "target_linearity": target_linearity,
                "support_linearity": support_linearity,
            }
        )
    if not diagnostics:
        return None, diagnostics
    robust_angle = statistics.median(
        item["angle_deg"] for item in diagnostics
    )
    return float(robust_angle), diagnostics


__all__ = [
    "CONTINUATION_MIN_EXTENSION_MM",
    "CONTINUATION_MAX_SKELETON_DISTANCE_MM",
    "CONTINUATION_MAX_ANGLE_DEG",
    "CONTINUATION_TANGENT_SPAN_MM",
    "CONTINUATION_PCA_SPANS_MM",
    "DISTAL_TANGENT_TRIM_MM",
    "DISTAL_TANGENT_FIT_SPAN_MM",
    "angle_deg",
    "chunk_vectors",
    "path_length",
    "max_local_turn",
    "skeleton_features",
    "distal_tangent",
    "continuation_tangent",
    "multiscale_continuation_angle",
]
