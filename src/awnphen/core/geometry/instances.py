"""Prediction / annotation instance geometry helpers.

这些函数只负责：
- 将 page_rings 转成有效 Shapely geometry；
- 展平 Polygon / MultiPolygon / GeometryCollection；
- 把 JSON record materialize 成带 geometry 的 item；
- 计算 mask geometry IoU。

不包含 centerline、measurement、assignment 或 evaluation 语义。
"""

from __future__ import annotations

import numpy as np
from shapely import Polygon, make_valid
from shapely.ops import unary_union


def parts(geometry):
    """递归提取 geometry 中所有有面积的 Polygon。"""
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > 1e-9 else []
    return [polygon for child in getattr(geometry, "geoms", []) for polygon in parts(child)]


def geometry_from_rings(rings):
    """把 ring list 转成有效的 Polygon/MultiPolygon geometry。"""
    polygons = []
    for ring in rings:
        points = np.asarray(ring, dtype=float).reshape(-1, 2)
        if len(points) >= 3:
            polygons.extend(parts(make_valid(Polygon(points))))
    return unary_union(polygons) if polygons else Polygon()


def load_items(records):
    """Materialize page-rings records，保留原始 record_index。"""
    result = []
    for index, item in enumerate(records):
        geometry = geometry_from_rings(item["page_rings"])
        if geometry.is_empty:
            continue
        result.append({**item, "record_index": index, "geometry": geometry})
    return result


def mask_iou(a, b):
    """计算两个 Shapely mask geometry 的 IoU。"""
    if not a.intersects(b):
        return 0.0
    intersection = a.intersection(b).area
    return float(intersection / max(1e-9, a.area + b.area - intersection))
