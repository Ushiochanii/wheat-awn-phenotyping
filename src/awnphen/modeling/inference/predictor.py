"""滑窗 YOLO 预测与跨 tile 合并。

这个模块只负责 inference 层最基础的两件事：
1. 在每个 tile 上得到实例 mask，并恢复到整页坐标；
2. 只在两个 tile 的重叠区域证据足够一致时，把它们合并为同一实例。

这里不做芒的断裂补救，也不使用 ground truth。
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from shapely import Polygon, box, make_valid
from shapely.ops import unary_union

from awnphen.modeling.inference.merge import parts, rings_of


# 跨 tile 合并的冻结阈值。它们控制“同一实例的两个视图是否足够一致”。
MERGE = {
    "overlap_min_area_fraction": 0.45,
    "shared_window_mask_iou": 0.35,
    "minimum_intersection_area_px2": 8.0,
    "minimum_shared_extent_px": 24.0,
    "allow_same_tile_cluster_members": False,
}


def geometry(rings):
    """把一个或多个 polygon ring 转成有效的 Shapely geometry。"""
    return unary_union(
        [
            polygon
            for ring in rings
            for polygon in parts(
                make_valid(
                    Polygon(
                        np.array(ring).reshape(-1, 2)
                    )
                )
            )
        ]
    )


def predict(model, image, tiles, imgsz):
    """逐 tile 推理，并把 mask / bbox 坐标恢复到整页坐标系。"""
    predictions = []

    for tile_index, rect in enumerate(tiles):
        x, y, x2, y2 = rect
        crop = image[y:y2, x:x2]

        result = model.predict(
            crop,
            imgsz=imgsz,
            conf=0.25,
            iou=0.7,
            device=os.environ.get("AWNPHEN_DEVICE", "0"),
            verbose=False,
        )[0]
        if result.masks is None:
            continue

        for points, class_id, confidence, bounds in zip(
            result.masks.xy,
            result.boxes.cls.cpu(),
            result.boxes.conf.cpu(),
            result.boxes.xyxy.cpu().numpy(),
        ):
            if len(points) < 3:
                continue

            page_geometry = geometry(
                [
                    (
                        points
                        + [x, y]
                    )
                    .flatten()
                    .tolist()
                ]
            )
            if page_geometry.is_empty:
                continue

            predictions.append(
                {
                    "class_id": int(class_id),
                    "confidence": float(confidence),
                    "geometry": page_geometry,
                    "tile": tile_index,
                    "tile_xyxy": rect,
                    "box_xyxy": (
                        bounds
                        + [x, y, x, y]
                    ).tolist(),
                }
            )

    return predictions


def merge(predictions):
    """合并不同 tile 对同一实例的重复观察，不做外推或 gap fill。"""

    # Union-Find 用来把“互相同意”的预测聚成一个实例。
    parent = list(
        range(
            len(predictions)
        )
    )
    memberships = [
        {prediction["tile"]}
        for prediction in predictions
    ]

    def root(index):
        while parent[index] != index:
            parent[index] = parent[
                parent[index]
            ]
            index = parent[index]
        return index

    # 先按 tile 分组，只枚举真正有重叠的 tile pair 里的预测。
    #
    # 这与下面的几何判定完全等价，但避免先对所有 prediction 做 O(N²)
    # 扫描、再发现绝大多数 tile 根本不相交。斜向整页会产生更多 tiles /
    # fragments，这个索引对 orientation sweep 尤其重要。
    edges = []
    tile_members = {}
    tile_rects = {}
    for index, prediction in enumerate(predictions):
        tile_id = prediction["tile"]
        tile_members.setdefault(tile_id, []).append(index)
        tile_rects.setdefault(
            tile_id,
            tuple(prediction["tile_xyxy"]),
        )

    tile_ids = sorted(tile_members)
    for tile_pos_a, tile_a in enumerate(tile_ids):
        ax1, ay1, ax2, ay2 = tile_rects[tile_a]
        for tile_b in tile_ids[tile_pos_a + 1 :]:
            bx1, by1, bx2, by2 = tile_rects[tile_b]
            if (
                min(ax2, bx2) <= max(ax1, bx1)
                or min(ay2, by2) <= max(ay1, by1)
            ):
                continue

            shared_window = box(
                *tile_rects[tile_a]
            ).intersection(
                box(*tile_rects[tile_b])
            )
            if shared_window.is_empty:
                continue

            for raw_index_a in tile_members[tile_a]:
                for raw_index_b in tile_members[tile_b]:
                    # Normalize indices so edge tuples preserve the same
                    # deterministic tie-breaking as the original all-pairs loop.
                    index_a, index_b = sorted(
                        (raw_index_a, raw_index_b)
                    )
                    prediction_a = predictions[index_a]
                    prediction_b = predictions[index_b]

                    if (
                        prediction_a["class_id"]
                        != prediction_b["class_id"]
                    ):
                        continue

                    ax1, ay1, ax2, ay2 = prediction_a[
                        "geometry"
                    ].bounds
                    bx1, by1, bx2, by2 = prediction_b[
                        "geometry"
                    ].bounds
                    if (
                        ax2 < bx1
                        or bx2 < ax1
                        or ay2 < by1
                        or by2 < ay1
                    ):
                        continue

                    if not prediction_a[
                        "geometry"
                    ].intersects(
                        prediction_b[
                            "geometry"
                        ]
                    ):
                        continue

                    intersection = prediction_a[
                        "geometry"
                    ].intersection(
                        prediction_b[
                            "geometry"
                        ]
                    )
                    intersection_area = (
                        intersection.area
                    )
                    if (
                        intersection_area
                        < MERGE[
                            "minimum_intersection_area_px2"
                        ]
                    ):
                        continue

                    overlap_fraction = (
                        intersection_area
                        / min(
                            prediction_a[
                                "geometry"
                            ].area,
                            prediction_b[
                                "geometry"
                            ].area,
                        )
                    )

                    geometry_a_shared = (
                        prediction_a[
                            "geometry"
                        ].intersection(
                            shared_window
                        )
                    )
                    geometry_b_shared = (
                        prediction_b[
                            "geometry"
                        ].intersection(
                            shared_window
                        )
                    )
                    local_iou = (
                        intersection_area
                        / max(
                            1e-9,
                            geometry_a_shared.union(
                                geometry_b_shared
                            ).area,
                        )
                    )

                    x, y, x2, y2 = (
                        intersection.bounds
                    )
                    shared_extent = max(
                        x2 - x,
                        y2 - y,
                    )

                    if (
                        overlap_fraction
                        >= MERGE[
                            "overlap_min_area_fraction"
                        ]
                        and local_iou
                        >= MERGE[
                            "shared_window_mask_iou"
                        ]
                        and shared_extent
                        >= MERGE[
                            "minimum_shared_extent_px"
                        ]
                    ):
                        edges.append(
                            (
                                local_iou,
                                overlap_fraction,
                                index_a,
                                index_b,
                            )
                        )

    # 从最可信的边开始合并，同时禁止一个 cluster 重复使用同一 tile。
    accepted = []
    for (
        local_iou,
        overlap_fraction,
        index_a,
        index_b,
    ) in sorted(
        edges,
        reverse=True,
    ):
        root_a = root(index_a)
        root_b = root(index_b)

        if (
            root_a == root_b
            or memberships[
                root_a
            ]
            & memberships[
                root_b
            ]
        ):
            continue

        parent[root_b] = root_a
        memberships[root_a] |= (
            memberships[root_b]
        )
        accepted.append(
            {
                "a": index_a,
                "b": index_b,
                "shared_iou": local_iou,
                "overlap_min": (
                    overlap_fraction
                ),
            }
        )

    groups = {}
    for index in range(
        len(predictions)
    ):
        groups.setdefault(
            root(index),
            [],
        ).append(index)

    merged = []
    for source_indices in (
        groups.values()
    ):
        source_predictions = [
            predictions[index]
            for index in source_indices
        ]
        merged.append(
            {
                "class_id": (
                    source_predictions[
                        0
                    ][
                        "class_id"
                    ]
                ),
                "confidence": max(
                    prediction[
                        "confidence"
                    ]
                    for prediction
                    in source_predictions
                ),
                "geometry": unary_union(
                    [
                        prediction[
                            "geometry"
                        ]
                        for prediction
                        in source_predictions
                    ]
                ),
                "source_prediction_indices": (
                    source_indices
                ),
                "source_tiles": [
                    prediction[
                        "tile"
                    ]
                    for prediction
                    in source_predictions
                ],
            }
        )

    return merged, accepted


def save_overlay(
    image,
    items,
    path,
):
    """保存整页 mask overlay，便于快速人工核对推理结果。"""
    canvas = image.copy()
    fill = image.copy()

    for item in items:
        color = (
            (40, 60, 235)
            if item["class_id"] == 0
            else (230, 150, 15)
        )
        for ring in rings_of(
            item["geometry"]
        ):
            points = np.rint(
                np.array(
                    ring
                ).reshape(
                    -1,
                    2,
                )
            ).astype(
                np.int32
            )
            cv2.fillPoly(
                fill,
                [points],
                color,
            )
            cv2.polylines(
                canvas,
                [points],
                True,
                color,
                2,
            )

    canvas = cv2.addWeighted(
        canvas,
        0.8,
        fill,
        0.2,
        0,
    )
    cv2.imwrite(
        str(path),
        canvas,
        [
            cv2.IMWRITE_JPEG_QUALITY,
            93,
        ],
    )


def serialize(items):
    """把 Shapely geometry 转回可写入 JSON 的 page_rings。"""
    return [
        {
            **{
                key: value
                for key, value
                in item.items()
                if key != "geometry"
            },
            "page_rings": rings_of(
                item["geometry"]
            ),
        }
        for item in items
    ]


__all__ = [
    "MERGE",
    "geometry",
    "predict",
    "merge",
    "save_overlay",
    "serialize",
]
