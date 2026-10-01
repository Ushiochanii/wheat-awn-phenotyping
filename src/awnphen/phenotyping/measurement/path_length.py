"""中心线路径的物理长度换算。

这个模块只负责纯几何/物理尺度换算，不负责：
- 网格检测；
- phenotype presence/absence 解释；
- accession / repeat / bottom-middle-top assignment。

Phase 1 从历史 scripts/evaluation/calibrate_grid_and_convert_lengths.py 中抽取。
"""

from __future__ import annotations

import numpy as np

GRID_MM = 5.0


def calibrated_path_length_mm(
    path,
    x_period_px,
    y_period_px,
    *,
    grid_mm=GRID_MM,
):
    """按独立 x/y 网格周期，把像素路径长度换算成毫米。"""
    if len(path) < 2:
        return 0.0

    sx = grid_mm / x_period_px
    sy = grid_mm / y_period_px
    points = np.asarray(path, dtype=float)
    delta = np.diff(points, axis=0)
    return float(
        np.sum(
            np.sqrt(
                (delta[:, 0] * sx) ** 2
                + (delta[:, 1] * sy) ** 2
            )
        )
    )
