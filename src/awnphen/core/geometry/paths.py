"""通用 polyline / path 几何 helper。

这些函数只处理二维坐标路径，不包含 awn、spikelet、association 或 measurement policy。
"""

from __future__ import annotations

import math

import numpy as np


def unsigned_angle_deg(a, b) -> float:
    """返回两个二维方向的无符号夹角，范围 0–90°。

    方向相反的共线向量视为同一 line orientation，因此使用 abs(dot)。
    零长度向量保持历史行为并返回 90°。
    """
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    na = np.linalg.norm(aa)
    nb = np.linalg.norm(bb)
    if na < 1e-9 or nb < 1e-9:
        return 90.0
    cosine = abs(float(np.dot(aa, bb) / (na * nb)))
    return math.degrees(math.acos(np.clip(cosine, -1.0, 1.0)))


def path_length(path) -> float:
    """返回二维 polyline 的欧氏像素长度。"""
    points = np.asarray(path, dtype=float)
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def endpoint_tangent(
    path,
    endpoint: int,
    target_span_px: float = 28.0,
) -> np.ndarray:
    """从指定 path endpoint 向路径内部估计单位切向量。

    endpoint=0 表示 path[0]；endpoint=1 表示 path[-1]。
    行为保持历史 multicomponent centerline helper 不变。
    """
    points = np.asarray(path, dtype=float)
    if endpoint == 1:
        points = points[::-1]

    origin = points[0]
    cumulative = 0.0
    chosen = points[min(1, len(points) - 1)]

    for i in range(1, len(points)):
        cumulative += float(np.linalg.norm(points[i] - points[i - 1]))
        chosen = points[i]
        if cumulative >= target_span_px:
            break

    vector = chosen - origin
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-9 else np.asarray([1.0, 0.0])


def connector_points(a, b) -> list[list[float]]:
    """在两个二维点之间生成历史 centerline 使用的线性 connector 点。"""
    start = np.asarray(a, dtype=float)
    end = np.asarray(b, dtype=float)
    distance = float(np.linalg.norm(end - start))
    steps = max(1, int(math.ceil(distance)))

    # 第一个点已经存在于 assembled path，因此保持历史行为并排除 t=0。
    return [
        ((1.0 - t) * start + t * end).tolist()
        for t in np.linspace(0.0, 1.0, steps + 1)[1:]
    ]
