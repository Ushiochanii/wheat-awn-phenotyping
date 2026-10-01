"""Raster / skeleton graph primitives used by awn centerline extraction.

这里只保存与图像骨架图本身有关的基础操作：
- geometry rasterization；
- skeleton connected-component selection；
- grid-neighbor graph shortest path；
- skeleton diameter。

不包含 spikelet association、representative selection、measurement policy 或 evaluation。
"""

from __future__ import annotations

import heapq
import math

import cv2
import numpy as np
from skimage.morphology import skeletonize

from awnphen.core.geometry.instances import parts

NEIGHBORS = [
    (dx, dy, math.hypot(dx, dy))
    for dy in (-1, 0, 1)
    for dx in (-1, 0, 1)
    if dx or dy
]


def rasterize(geometry, pad=4):
    minx, miny, maxx, maxy = geometry.bounds
    x0 = int(math.floor(minx)) - pad
    y0 = int(math.floor(miny)) - pad
    x1 = int(math.ceil(maxx)) + pad
    y1 = int(math.ceil(maxy)) + pad
    width = max(1, x1 - x0 + 1)
    height = max(1, y1 - y0 + 1)
    mask = np.zeros((height, width), np.uint8)
    for polygon in parts(geometry):
        points = np.rint(
            np.asarray(polygon.exterior.coords)[:, :2] - [x0, y0]
        ).astype(np.int32)
        cv2.fillPoly(mask, [points], 1)
    return mask, (x0, y0)


def largest_skeleton_component(mask):
    skel = skeletonize(mask > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(skel, 8)
    if count <= 1:
        return set()
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.where(labels == component)
    return set(zip(xs.tolist(), ys.tolist()))


def dijkstra(nodes, start):
    distances = {start: 0.0}
    previous = {}
    queue = [(0.0, start)]
    while queue:
        distance, point = heapq.heappop(queue)
        if distance != distances.get(point):
            continue
        x, y = point
        for dx, dy, cost in NEIGHBORS:
            neighbor = (x + dx, y + dy)
            if neighbor not in nodes:
                continue
            candidate = distance + cost
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = point
                heapq.heappush(queue, (candidate, neighbor))
    return distances, previous


def skeleton_diameter(nodes):
    if len(nodes) < 2:
        return [], 0.0
    endpoints = [
        point
        for point in nodes
        if sum(
            (point[0] + dx, point[1] + dy) in nodes
            for dx, dy, _ in NEIGHBORS
        )
        == 1
    ]
    candidates = endpoints if len(endpoints) >= 2 else list(nodes)
    start = candidates[0]
    distances, _ = dijkstra(nodes, start)
    reachable = [point for point in candidates if point in distances]
    if len(reachable) < 2:
        return [], 0.0
    a = max(reachable, key=distances.__getitem__)
    distances, previous = dijkstra(nodes, a)
    reachable = [
        point
        for point in candidates
        if point in distances and point != a
    ]
    if not reachable:
        return [], 0.0
    b = max(reachable, key=distances.__getitem__)
    path = [b]
    while path[-1] != a:
        if path[-1] not in previous:
            return [], 0.0
        path.append(previous[path[-1]])
    path.reverse()
    return path, float(distances[b])
