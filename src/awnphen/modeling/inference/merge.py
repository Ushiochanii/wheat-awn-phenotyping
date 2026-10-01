"""推理结果的去重与芒片段拼接。

这里处理的是 prediction 自身的几何关系：
- dedupe：去掉重复预测；
- stitch_awns：在端点、方向、宽度等证据都足够时连接断裂芒。

全过程不读取 ground truth，因此可以安全用于正式 inference。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from shapely import Point, Polygon, make_valid
from shapely.ops import unary_union

from awnphen.core.geometry.paths import unsigned_angle_deg

@dataclass
class ShapeDescriptor:
    endpoints: tuple[np.ndarray, np.ndarray]
    tangents: tuple[np.ndarray, np.ndarray]
    width: float
    skeleton_pixels: int
    anchor_id: int | None
    base_endpoint: int | None
    anchor_distance: float | None


def parts(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > 1e-9 else []
    return [p for g in getattr(geometry, "geoms", []) for p in parts(g)]


def geometry_from_rings(rings):
    polygons = []
    for ring in rings:
        points = np.asarray(ring, dtype=float).reshape(-1, 2)
        if len(points) < 3:
            continue
        polygons.extend(parts(make_valid(Polygon(points))))
    return unary_union(polygons) if polygons else Polygon()


def rings_of(geometry):
    return [np.asarray(p.exterior.coords)[:-1].flatten().tolist() for p in parts(geometry)]


def load_items(records):
    result = []
    for idx, item in enumerate(records):
        g = geometry_from_rings(item["page_rings"])
        if g.is_empty:
            continue
        result.append(
            {
                **{k: v for k, v in item.items() if k != "page_rings"},
                "geometry": g,
                "members": item.get("postprocess_members", [idx]),
                "source_tiles": sorted(set(item.get("source_tiles", [item.get("tile")])) - {None}),
            }
        )
    return result


def serialize(items):
    answer = []
    for item in items:
        answer.append(
            {
                **{k: v for k, v in item.items() if k != "geometry"},
                "page_rings": rings_of(item["geometry"]),
            }
        )
    return answer


def bounds_distance(bounds_a, bounds_b):
    """Lower bound on Euclidean distance between two axis-aligned boxes."""
    ax1, ay1, ax2, ay2 = bounds_a
    bx1, by1, bx2, by2 = bounds_b
    dx = max(0.0, bx1 - ax2, ax1 - bx2)
    dy = max(0.0, by1 - ay2, ay1 - by2)
    return math.hypot(dx, dy)


def intersection_stats(a, b, buffer_px=0.0):
    ga = a.buffer(buffer_px) if buffer_px else a
    gb = b.buffer(buffer_px) if buffer_px else b
    if not ga.intersects(gb):
        return 0.0, 0.0
    inter = ga.intersection(gb).area
    union = ga.area + gb.area - inter
    return inter / max(1e-9, union), inter / max(1e-9, min(ga.area, gb.area))


def angle_deg(a, b):
    """Compatibility wrapper for the historical stitching import path."""
    return unsigned_angle_deg(a, b)


def raster_skeleton(geometry, pad=3):
    minx, miny, maxx, maxy = geometry.bounds
    x0 = int(math.floor(minx)) - pad
    y0 = int(math.floor(miny)) - pad
    x1 = int(math.ceil(maxx)) + pad
    y1 = int(math.ceil(maxy)) + pad
    width = max(1, x1 - x0 + 1)
    height = max(1, y1 - y0 + 1)
    mask = np.zeros((height, width), np.uint8)
    for polygon in parts(geometry):
        points = np.rint(np.asarray(polygon.exterior.coords)[:, :2] - [x0, y0]).astype(np.int32)
        cv2.fillPoly(mask, [points], 255)

    # Morphological skeleton avoids an opencv-contrib dependency. Awn masks are thin,
    # so the loop is short in practice.
    work = mask.copy()
    skeleton = np.zeros_like(work)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(work):
        eroded = cv2.erode(work, kernel)
        opened = cv2.dilate(eroded, kernel)
        skeleton = cv2.bitwise_or(skeleton, cv2.subtract(work, opened))
        work = eroded
    ys, xs = np.nonzero(skeleton)
    return skeleton, np.column_stack([xs + x0, ys + y0]).astype(float), (x0, y0)


def pca_endpoints(geometry):
    coords = np.concatenate([np.asarray(p.exterior.coords)[:-1, :2] for p in parts(geometry)], axis=0)
    center = coords.mean(axis=0)
    covariance = np.cov(coords - center, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    projections = (coords - center) @ axis
    return coords[int(np.argmin(projections))], coords[int(np.argmax(projections))], axis


def tangent_near(endpoint, skeleton_points, radius=35.0):
    distances = np.linalg.norm(skeleton_points - endpoint, axis=1)
    nearby = skeleton_points[distances <= radius]
    if len(nearby) < 3:
        nearby = skeleton_points[np.argsort(distances)[: min(12, len(skeleton_points))]]
    if len(nearby) < 2:
        return np.array([1.0, 0.0])
    centered = nearby - nearby.mean(axis=0)
    covariance = np.cov(centered, rowvar=False)
    values, vectors = np.linalg.eigh(covariance)
    return vectors[:, int(np.argmax(values))]


def describe(geometry, spikelets, anchor_distance):
    skeleton, points, offset = raster_skeleton(geometry)
    if len(points) >= 2:
        binary = (skeleton > 0).astype(np.uint8)
        counts = cv2.filter2D(binary, -1, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT)
        ys, xs = np.nonzero((binary > 0) & (counts <= 2))
        endpoints = np.column_stack([xs + offset[0], ys + offset[1]]).astype(float)
        if len(endpoints) >= 2:
            # Farthest endpoint pair is robust to small skeleton spurs.
            distances = np.linalg.norm(endpoints[:, None, :] - endpoints[None, :, :], axis=2)
            i, j = np.unravel_index(int(np.argmax(distances)), distances.shape)
            ep0, ep1 = endpoints[i], endpoints[j]
        else:
            ep0, ep1, _ = pca_endpoints(geometry)
    else:
        ep0, ep1, _ = pca_endpoints(geometry)
        points = np.vstack([ep0, ep1])

    tangents = (tangent_near(ep0, points), tangent_near(ep1, points))
    centerline_len = max(1.0, float(len(points)))
    width = float(geometry.area / centerline_len)

    best = None
    for endpoint_id, endpoint in enumerate((ep0, ep1)):
        point = Point(float(endpoint[0]), float(endpoint[1]))
        for anchor_id, spikelet in enumerate(spikelets):
            distance = float(point.distance(spikelet["geometry"]))
            if best is None or distance < best[0]:
                best = (distance, anchor_id, endpoint_id)
    if best is not None and best[0] <= anchor_distance:
        anchor = best[1]
        base = best[2]
        distance = best[0]
    else:
        anchor = None
        base = None
        distance = best[0] if best is not None else None

    return ShapeDescriptor(
        endpoints=(ep0, ep1),
        tangents=tangents,
        width=width,
        skeleton_pixels=int(len(points)),
        anchor_id=anchor,
        base_endpoint=base,
        anchor_distance=distance,
    )


def merge_group(a, b, reason, score):
    return {
        "class_id": a["class_id"],
        "confidence": max(float(a.get("confidence", 0.0)), float(b.get("confidence", 0.0))),
        "geometry": unary_union([a["geometry"], b["geometry"]]),
        "members": sorted(set(a.get("members", [])) | set(b.get("members", []))),
        "source_tiles": sorted(set(a.get("source_tiles", [])) | set(b.get("source_tiles", []))),
        "postprocess_reason": sorted(
            set(a.get("postprocess_reason", [])) | set(b.get("postprocess_reason", [])) | {reason}
        ),
        "last_merge_score": float(score),
    }


def dedupe(
    items,
    duplicate_iou,
    duplicate_overlap,
    duplicate_buffer,
    forbid_shared_tiles=False,
    shared_tile_max_axis_angle=None,
    shared_tile_min_overlap=0.0,
):
    items = list(items)
    merges = []
    while True:
        best = None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i]["class_id"] != items[j]["class_id"]:
                    continue
                shared_tiles = set(items[i].get("source_tiles", [])) & set(items[j].get("source_tiles", []))
                # Exact early reject: both geometries are expanded by
                # duplicate_buffer before overlap scoring, so boxes farther
                # apart than twice that buffer cannot intersect.
                if bounds_distance(
                    items[i]["geometry"].bounds,
                    items[j]["geometry"].bounds,
                ) > 2.0 * float(duplicate_buffer):
                    continue
                iou, overlap = intersection_stats(
                    items[i]["geometry"], items[j]["geometry"], duplicate_buffer
                )
                if iou < duplicate_iou and overlap < duplicate_overlap:
                    continue
                if shared_tiles and forbid_shared_tiles:
                    # Same-tile coexistence is strong evidence for distinct instances, but
                    # nearly collinear masks that almost cover one another can still be
                    # duplicate predictions that survived per-tile NMS.
                    if shared_tile_max_axis_angle is None:
                        continue
                    _, _, axis_i = pca_endpoints(items[i]["geometry"])
                    _, _, axis_j = pca_endpoints(items[j]["geometry"])
                    axis_difference = angle_deg(axis_i, axis_j)
                    if axis_difference > shared_tile_max_axis_angle or overlap < shared_tile_min_overlap:
                        continue
                score = max(iou / max(duplicate_iou, 1e-9), overlap / max(duplicate_overlap, 1e-9))
                if best is None or score > best[0]:
                    best = (score, i, j, iou, overlap)
        if best is None:
            break
        score, i, j, iou, overlap = best
        left, right = items[i], items[j]
        def representative_key(item):
            minx, miny, maxx, maxy = item["geometry"].bounds
            span = math.hypot(maxx - minx, maxy - miny)
            return (span, float(item.get("confidence", 0.0)))

        winner = max((left, right), key=representative_key)
        merged = {
            **winner,
            "geometry": winner["geometry"],
            "confidence": max(float(left.get("confidence", 0.0)), float(right.get("confidence", 0.0))),
            "members": sorted(set(left.get("members", [])) | set(right.get("members", []))),
            "source_tiles": sorted(set(left.get("source_tiles", [])) | set(right.get("source_tiles", []))),
            "postprocess_reason": sorted(
                set(left.get("postprocess_reason", []))
                | set(right.get("postprocess_reason", []))
                | {"duplicate_representative"}
            ),
            "last_merge_score": float(score),
        }
        merges.append(
            {
                "members_a": left.get("members", []),
                "members_b": right.get("members", []),
                "iou_buffered": iou,
                "overlap_min_buffered": overlap,
            }
        )
        items = [x for k, x in enumerate(items) if k not in (i, j)] + [merged]
    return items, merges


def best_fragment_pair(items, spikelets, args):
    # Only items whose bounding boxes are within max_gap can possibly have
    # endpoint distance <= max_gap. Build this exact candidate set first so
    # isolated predictions do not pay the expensive skeleton-description cost.
    candidate_pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a["class_id"] != 0 or b["class_id"] != 0:
                continue
            if set(a.get("source_tiles", [])) & set(b.get("source_tiles", [])):
                continue
            if bounds_distance(
                a["geometry"].bounds,
                b["geometry"].bounds,
            ) > args.max_gap:
                continue
            candidate_pairs.append((i, j))

    if not candidate_pairs:
        return None

    needed = sorted({index for pair in candidate_pairs for index in pair})
    descriptors = {
        index: describe(items[index]["geometry"], spikelets, args.anchor_distance)
        for index in needed
    }
    best = None
    for i, j in candidate_pairs:
        a, b = items[i], items[j]
        da, db = descriptors[i], descriptors[j]

        # Two independently spikelet-anchored predictions are likely distinct
        # awns, even when they emerge from the same spikelet.
        if da.anchor_id is not None and db.anchor_id is not None:
            continue
        width_ratio = max(da.width, db.width) / max(
            1e-6,
            min(da.width, db.width),
        )
        if width_ratio > args.max_width_ratio:
            continue

        for ea in (0, 1):
            # Never extend a spikelet-anchored fragment through its base.
            if da.base_endpoint is not None and ea == da.base_endpoint:
                continue
            for eb in (0, 1):
                if db.base_endpoint is not None and eb == db.base_endpoint:
                    continue
                pa, pb = da.endpoints[ea], db.endpoints[eb]
                gap = float(np.linalg.norm(pb - pa))
                if gap > args.max_gap:
                    continue
                tangent_angle = angle_deg(da.tangents[ea], db.tangents[eb])
                if tangent_angle > args.max_tangent_angle:
                    continue
                connector = pb - pa
                align_a = angle_deg(da.tangents[ea], connector)
                align_b = angle_deg(db.tangents[eb], connector)
                connector_angle = max(align_a, align_b)
                if connector_angle > args.max_connector_angle:
                    continue

                gap_score = 1.0 - gap / args.max_gap
                tangent_score = 1.0 - tangent_angle / args.max_tangent_angle
                connector_score = 1.0 - connector_angle / args.max_connector_angle
                width_score = 1.0 - min(
                    1.0,
                    (width_ratio - 1.0)
                    / max(1e-9, args.max_width_ratio - 1.0),
                )
                anchor_bonus = (
                    0.08
                    if (da.anchor_id is None) != (db.anchor_id is None)
                    else 0.0
                )
                score = (
                    0.42 * gap_score
                    + 0.24 * tangent_score
                    + 0.24 * connector_score
                    + 0.10 * width_score
                    + anchor_bonus
                )
                if score < args.minimum_join_score:
                    continue
                candidate = {
                    "score": float(score),
                    "i": i,
                    "j": j,
                    "endpoint_a": ea,
                    "endpoint_b": eb,
                    "gap_px": gap,
                    "tangent_angle_deg": tangent_angle,
                    "connector_angle_deg": connector_angle,
                    "width_ratio": width_ratio,
                    "anchor_a": da.anchor_id,
                    "anchor_b": db.anchor_id,
                }
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
    return best

def stitch_awns(items, spikelets, args):
    work = list(items)
    joins = []
    while True:
        candidate = best_fragment_pair(work, spikelets, args)
        if candidate is None:
            break
        i, j = candidate["i"], candidate["j"]
        left, right = work[i], work[j]
        merged = merge_group(left, right, "endpoint_continuity", candidate["score"])
        joins.append(
            {
                **candidate,
                "members_a": left.get("members", []),
                "members_b": right.get("members", []),
                "members_merged": merged["members"],
            }
        )
        work = [x for k, x in enumerate(work) if k not in (i, j)] + [merged]
    return work, joins

__all__ = ["ShapeDescriptor", "parts", "geometry_from_rings", "rings_of", "load_items", "serialize", "intersection_stats", "angle_deg", "raster_skeleton", "pca_endpoints", "tangent_near", "describe", "merge_group", "dedupe", "best_fragment_pair", "stitch_awns"]
