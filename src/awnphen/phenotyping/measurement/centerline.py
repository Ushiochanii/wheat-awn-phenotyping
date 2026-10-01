"""代表芒中心线提取与断裂片段连接。

目标不是“画一条看起来顺的线”，而是得到可审计、可测长度的物理路径：
- 每个 mask component 先骨架化；
- 从靠近小穗的一端确定 root；
- 多 component 时按冻结的几何规则判断能否连接；
- 不满足规则的断裂保持 review，而不是为了长度好看强行补线。

<= 8 px 的 micro-gap 保留历史冻结策略：connector angle 只记录，不参与该处
gate/score；其它 tangent、outward、gap、ambiguity 规则保持不变。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from shapely import Point
from skimage.morphology import skeletonize

from awnphen.core.geometry.instances import parts
from awnphen.core.geometry.paths import (
    connector_points,
    endpoint_tangent,
    path_length,
    unsigned_angle_deg,
)
from awnphen.core.geometry.skeleton import (
    NEIGHBORS,
    dijkstra,
    largest_skeleton_component,
    rasterize,
)

# Frozen historical v1/v2 centerline policy constants.
MAX_GAP_PX = 70.0
MAX_TANGENT_ANGLE_DEG = 22.0
MAX_CONNECTOR_ANGLE_DEG = 26.0
MIN_JOIN_SCORE = 0.54
MIN_COMPONENT_LENGTH_PX = 5.0
OUTWARD_DISTANCE_TOLERANCE_PX = 8.0

# Root-selection and micro-gap development rules.
ROOT_BASE_ENVELOPE_PX = 12.0
MICRO_GAP_PX = 8.0


@dataclass
class SkeletonComponent:
    component_index: int
    nodes: set[tuple[int, int]]
    endpoints: list[tuple[int, int]]
    offset: tuple[int, int]


def skeleton_component(
    polygon,
    component_index: int,
) -> SkeletonComponent | None:
    mask, offset = rasterize(polygon)
    nodes = largest_skeleton_component(mask)
    if len(nodes) < 2:
        return None

    endpoints = [
        point
        for point in nodes
        if sum(
            (point[0] + dx, point[1] + dy) in nodes
            for dx, dy, _ in NEIGHBORS
        )
        == 1
    ]
    if not endpoints:
        # Rare loop-like skeleton. Keep graph usable by allowing all nodes as
        # candidate anchors/tips, matching the historical diameter fallback spirit.
        endpoints = list(nodes)

    return SkeletonComponent(
        component_index=component_index,
        nodes=nodes,
        endpoints=endpoints,
        offset=(int(offset[0]), int(offset[1])),
    )


def global_point(
    component: SkeletonComponent,
    local_point,
) -> np.ndarray:
    return np.asarray(
        [
            float(local_point[0] + component.offset[0]),
            float(local_point[1] + component.offset[1]),
        ],
        dtype=float,
    )


def rooted_path(
    component: SkeletonComponent,
    root_local,
) -> tuple[list[list[float]], float]:
    """Shortest-path-tree root to geodesically farthest skeleton endpoint."""
    distances, previous = dijkstra(component.nodes, root_local)
    candidates = [
        point
        for point in component.endpoints
        if point != root_local and point in distances
    ]
    if not candidates:
        candidates = [
            point
            for point in component.nodes
            if point != root_local and point in distances
        ]
    if not candidates:
        return [], 0.0

    tip = max(candidates, key=distances.__getitem__)
    local_path = [tip]
    while local_path[-1] != root_local:
        parent = previous.get(local_path[-1])
        if parent is None:
            return [], 0.0
        local_path.append(parent)

    local_path.reverse()
    path = [
        [
            float(x + component.offset[0]),
            float(y + component.offset[1]),
        ]
        for x, y in local_path
    ]
    return path, float(distances[tip])


def nearest_spikelet_root(
    components: list[SkeletonComponent],
    spikelets,
):
    """Choose physical parent by nearest endpoint, then robust rooted component.

    The globally nearest endpoint first identifies the parent spikelet. Among component
    endpoints within the same 12 px accepted-association envelope of that parent, the
    longest rooted geodesic component wins. Base distance only breaks ties inside this
    envelope.
    """
    nearest = None
    endpoint_records = []

    for component_list_index, component in enumerate(components):
        for endpoint_local in component.endpoints:
            point_xy = global_point(component, endpoint_local)
            point = Point(float(point_xy[0]), float(point_xy[1]))

            for spikelet_index, spikelet in enumerate(spikelets):
                distance = float(point.distance(spikelet["geometry"]))
                record = (
                    distance,
                    component_list_index,
                    endpoint_local,
                    spikelet_index,
                )
                endpoint_records.append(record)

                if nearest is None or (
                    distance,
                    component_list_index,
                    spikelet_index,
                ) < (
                    nearest[0],
                    nearest[1],
                    nearest[3],
                ):
                    nearest = record

    if nearest is None:
        return None

    parent = int(nearest[3])
    candidates = []

    for (
        distance,
        component_list_index,
        endpoint_local,
        spikelet_index,
    ) in endpoint_records:
        if (
            int(spikelet_index) != parent
            or distance > ROOT_BASE_ENVELOPE_PX
        ):
            continue

        path, length = rooted_path(
            components[component_list_index],
            endpoint_local,
        )
        if len(path) < 2 or length < MIN_COMPONENT_LENGTH_PX:
            continue

        candidates.append(
            (
                float(length),
                -float(distance),
                component_list_index,
                endpoint_local,
                parent,
                float(distance),
            )
        )

    if not candidates:
        return nearest

    # Longest rooted component wins; closer base endpoint breaks ties.
    (
        _length,
        _neg_distance,
        component_list_index,
        endpoint_local,
        parent,
        distance,
    ) = max(candidates)

    return (
        distance,
        component_list_index,
        endpoint_local,
        parent,
    )


def extract_centerline_multicomponent_v2_rooted(
    item,
    spikelets,
    max_gap_px: float = MAX_GAP_PX,
    max_tangent_angle_deg: float = MAX_TANGENT_ANGLE_DEG,
    max_connector_angle_deg: float = MAX_CONNECTOR_ANGLE_DEG,
    minimum_join_score: float = MIN_JOIN_SCORE,
):
    """Extract the canonical rooted multi-component centerline."""
    polygons = parts(item["geometry"])
    components = [
        skeleton_component(polygon, index)
        for index, polygon in enumerate(polygons)
    ]
    components = [
        component
        for component in components
        if component is not None
    ]

    if not components:
        return {
            "status": "invalid_centerline",
            "path": [],
            "length_px": 0.0,
            "component_count": len(polygons),
            "usable_component_count": 0,
            "joined_component_count": 0,
            "unused_component_count": 0,
            "joins": [],
            "orientation": None,
            "rooted_branch_selection": True,
        }

    anchor = nearest_spikelet_root(components, spikelets)
    if anchor is None:
        # No predicted spikelet anchors. Preserve the historical reviewable fallback:
        # choose the longest rooted endpoint path across all components.
        best = None
        for component_list_index, component in enumerate(components):
            for endpoint in component.endpoints:
                path, length = rooted_path(component, endpoint)
                if best is None or length > best[0]:
                    best = (
                        length,
                        component_list_index,
                        endpoint,
                        path,
                    )

        length, _component_list_index, _endpoint, path = best
        return {
            "status": "no_spikelet_anchor",
            "path": path,
            "length_px": float(length),
            "component_count": len(polygons),
            "usable_component_count": len(components),
            "joined_component_count": 1,
            "unused_component_count": max(
                0,
                len(components) - 1,
            ),
            "joins": [],
            "orientation": None,
            "rooted_branch_selection": True,
        }

    (
        base_distance,
        root_index,
        root_endpoint_local,
        parent_spikelet_index,
    ) = anchor

    parent_geometry = spikelets[parent_spikelet_index]["geometry"]
    root_component = components[root_index]
    assembled, root_length = rooted_path(
        root_component,
        root_endpoint_local,
    )

    if (
        len(assembled) < 2
        or root_length < MIN_COMPONENT_LENGTH_PX
    ):
        return {
            "status": "invalid_rooted_centerline",
            "path": assembled,
            "length_px": float(root_length),
            "component_count": len(polygons),
            "usable_component_count": len(components),
            "joined_component_count": 1,
            "unused_component_count": max(
                0,
                len(components) - 1,
            ),
            "joins": [],
            "orientation": None,
            "rooted_branch_selection": True,
        }

    used = {root_index}
    joins = []
    ambiguous = False

    while True:
        current_tip = np.asarray(
            assembled[-1],
            dtype=float,
        )
        current_tangent = endpoint_tangent(
            assembled,
            1,
        )
        current_distance = float(
            Point(
                float(current_tip[0]),
                float(current_tip[1]),
            ).distance(parent_geometry)
        )
        candidates = []

        for component_list_index, component in enumerate(components):
            if component_list_index in used:
                continue

            for near_endpoint_local in component.endpoints:
                oriented, component_length = rooted_path(
                    component,
                    near_endpoint_local,
                )
                if (
                    len(oriented) < 2
                    or component_length < MIN_COMPONENT_LENGTH_PX
                ):
                    continue

                near = np.asarray(
                    oriented[0],
                    dtype=float,
                )
                far = np.asarray(
                    oriented[-1],
                    dtype=float,
                )
                gap = float(
                    np.linalg.norm(
                        near - current_tip
                    )
                )
                if gap > max_gap_px:
                    continue

                near_distance = float(
                    Point(
                        float(near[0]),
                        float(near[1]),
                    ).distance(parent_geometry)
                )
                far_distance = float(
                    Point(
                        float(far[0]),
                        float(far[1]),
                    ).distance(parent_geometry)
                )

                if (
                    near_distance
                    + OUTWARD_DISTANCE_TOLERANCE_PX
                    < current_distance
                ):
                    continue
                if far_distance <= near_distance:
                    continue

                candidate_tangent = endpoint_tangent(
                    oriented,
                    0,
                )
                tangent_angle = unsigned_angle_deg(
                    current_tangent,
                    candidate_tangent,
                )
                if tangent_angle > max_tangent_angle_deg:
                    continue

                connector = near - current_tip
                if float(np.linalg.norm(connector)) < 1e-9:
                    connector_angle = 0.0
                else:
                    connector_angle = max(
                        unsigned_angle_deg(
                            current_tangent,
                            connector,
                        ),
                        unsigned_angle_deg(
                            candidate_tangent,
                            connector,
                        ),
                    )

                # Frozen development micro-gap rule:
                # connector direction at <=8 px is unstable to skeleton endpoint jitter.
                # Record the observed angle, but neutralize its gate/score contribution.
                micro_gap_connector_override = bool(
                    gap <= MICRO_GAP_PX
                )
                effective_connector_angle = (
                    0.0
                    if micro_gap_connector_override
                    else connector_angle
                )

                if (
                    effective_connector_angle
                    > max_connector_angle_deg
                ):
                    continue

                gap_score = 1.0 - gap / max_gap_px
                tangent_score = (
                    1.0
                    - tangent_angle
                    / max_tangent_angle_deg
                )
                connector_score = (
                    1.0
                    - effective_connector_angle
                    / max_connector_angle_deg
                )
                score = (
                    0.50 * gap_score
                    + 0.25 * tangent_score
                    + 0.25 * connector_score
                )
                if score < minimum_join_score:
                    continue

                candidates.append(
                    {
                        "score": float(score),
                        "component_list_index": component_list_index,
                        "component_index": component.component_index,
                        "near_endpoint_local": [
                            int(near_endpoint_local[0]),
                            int(near_endpoint_local[1]),
                        ],
                        "gap_px": gap,
                        "tangent_angle_deg": tangent_angle,
                        "connector_angle_deg": connector_angle,
                        "micro_gap_connector_override": (
                            micro_gap_connector_override
                        ),
                        "effective_connector_angle_deg": (
                            effective_connector_angle
                        ),
                        "near_distance_to_spikelet_px": (
                            near_distance
                        ),
                        "far_distance_to_spikelet_px": (
                            far_distance
                        ),
                        "rooted_component_length_px": float(
                            component_length
                        ),
                        "oriented_path": oriented,
                    }
                )

        if not candidates:
            break

        candidates.sort(
            key=lambda row: (
                -row["score"],
                row["gap_px"],
            )
        )
        if (
            len(candidates) >= 2
            and candidates[0]["score"]
            - candidates[1]["score"]
            < 0.04
        ):
            ambiguous = True
            break

        best = candidates[0]
        component_list_index = best[
            "component_list_index"
        ]
        oriented = best["oriented_path"]
        near = np.asarray(
            oriented[0],
            dtype=float,
        )

        assembled.extend(
            connector_points(
                current_tip,
                near,
            )
        )
        assembled.extend(oriented[1:])

        joins.append(
            {
                key: value
                for key, value in best.items()
                if key
                not in {
                    "component_list_index",
                    "oriented_path",
                }
            }
        )
        used.add(component_list_index)

    length = path_length(assembled)

    status = (
        "ok_joined_rooted"
        if joins
        else "ok_single_component_rooted"
    )
    if ambiguous:
        status = (
            "review_ambiguous_component_join_rooted"
        )
    elif len(used) < len(components):
        status = (
            "review_unused_components_rooted"
            if joins
            else "review_multicomponent_unjoined_rooted"
        )

    return {
        "status": status,
        "path": assembled,
        "length_px": float(length),
        "component_count": len(polygons),
        "usable_component_count": len(components),
        "joined_component_count": len(used),
        "unused_component_count": (
            len(components) - len(used)
        ),
        "joins": joins,
        "orientation": {
            "base": assembled[0],
            "tip": assembled[-1],
            "anchor_index": int(
                parent_spikelet_index
            ),
            "base_distance_to_nearest_spikelet_px": float(
                base_distance
            ),
        },
        "rooted_branch_selection": True,
        "root_component_index": int(
            root_component.component_index
        ),
        "root_endpoint_local": [
            int(root_endpoint_local[0]),
            int(root_endpoint_local[1]),
        ],
    }




@dataclass
class RasterSkeletonComponent:
    component_index: int
    nodes: set[tuple[int, int]]
    endpoints: list[tuple[int, int]]
    offset: tuple[int, int]
    pixel_area: int


def _raster_component_endpoints(nodes):
    endpoints = [
        point
        for point in nodes
        if sum(
            (point[0] + dx, point[1] + dy) in nodes
            for dx, dy, _ in NEIGHBORS
        )
        == 1
    ]
    return endpoints if endpoints else list(nodes)


def raster_skeleton_components(geometry):
    """Rasterize the whole geometry once and keep raster-connected skeleton parts."""
    mask, offset = rasterize(geometry)
    skeleton = skeletonize(mask > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(skeleton, 8)

    components = []
    for label in range(1, count):
        ys, xs = np.where(labels == label)
        nodes = set(zip(xs.tolist(), ys.tolist()))
        if len(nodes) < 2:
            continue
        components.append(
            RasterSkeletonComponent(
                component_index=len(components),
                nodes=nodes,
                endpoints=_raster_component_endpoints(nodes),
                offset=(int(offset[0]), int(offset[1])),
                pixel_area=int(stats[label, cv2.CC_STAT_AREA]),
            )
        )

    return components, mask, offset


def raster_global_point(component: RasterSkeletonComponent, local_point):
    return np.asarray(
        [
            float(local_point[0] + component.offset[0]),
            float(local_point[1] + component.offset[1]),
        ],
        dtype=float,
    )


def raster_rooted_path(component: RasterSkeletonComponent, root_local):
    distances, previous = dijkstra(component.nodes, root_local)
    candidates = [
        point
        for point in component.endpoints
        if point != root_local and point in distances
    ]
    if not candidates:
        candidates = [
            point
            for point in component.nodes
            if point != root_local and point in distances
        ]
    if not candidates:
        return [], 0.0

    tip = max(candidates, key=distances.__getitem__)
    local_path = [tip]
    while local_path[-1] != root_local:
        parent = previous.get(local_path[-1])
        if parent is None:
            return [], 0.0
        local_path.append(parent)
    local_path.reverse()

    path = [
        [
            float(x + component.offset[0]),
            float(y + component.offset[1]),
        ]
        for x, y in local_path
    ]
    return path, float(distances[tip])


def extract_raster_connected_rooted(item, spikelets):
    """Extract one rooted path from whole-geometry raster connectivity.

    This is the canonical form of the historical P7b raster-connectivity fallback.
    It never bridges disconnected raster components.
    """
    components, _mask, _offset = raster_skeleton_components(item["geometry"])
    vector_part_count = len(parts(item["geometry"]))

    if not components:
        return {
            "status": "invalid_raster_skeleton",
            "path": [],
            "length_px": 0.0,
            "vector_part_count": vector_part_count,
            "raster_component_count": 0,
        }

    endpoint_records = []
    nearest = None

    for component_index, component in enumerate(components):
        for endpoint in component.endpoints:
            point_xy = raster_global_point(component, endpoint)
            point = Point(float(point_xy[0]), float(point_xy[1]))

            for spikelet_index, spikelet in enumerate(spikelets):
                distance = float(point.distance(spikelet["geometry"]))
                record = (
                    distance,
                    component_index,
                    endpoint,
                    spikelet_index,
                )
                endpoint_records.append(record)

                if nearest is None or (
                    distance,
                    component_index,
                    spikelet_index,
                ) < (
                    nearest[0],
                    nearest[1],
                    nearest[3],
                ):
                    nearest = record

    if nearest is None:
        return {
            "status": "no_spikelet_anchor",
            "path": [],
            "length_px": 0.0,
            "vector_part_count": vector_part_count,
            "raster_component_count": len(components),
        }

    parent_spikelet_index = int(nearest[3])
    candidates = []

    for (
        distance,
        component_index,
        endpoint,
        spikelet_index,
    ) in endpoint_records:
        if (
            int(spikelet_index) != parent_spikelet_index
            or distance > ROOT_BASE_ENVELOPE_PX
        ):
            continue

        path, length = raster_rooted_path(
            components[component_index],
            endpoint,
        )
        if len(path) < 2 or length < MIN_COMPONENT_LENGTH_PX:
            continue

        candidates.append(
            (
                float(length),
                -float(distance),
                component_index,
                endpoint,
                parent_spikelet_index,
                float(distance),
                path,
            )
        )

    if not candidates:
        distance, component_index, endpoint, parent_spikelet_index = nearest
        path, length = raster_rooted_path(
            components[component_index],
            endpoint,
        )
        return {
            "status": "review_raster_root_outside_accepted_envelope",
            "path": path,
            "length_px": float(length),
            "vector_part_count": vector_part_count,
            "raster_component_count": len(components),
            "root_raster_component_index": int(component_index),
            "parent_spikelet_index": int(parent_spikelet_index),
            "base_distance_px": float(distance),
            "root_endpoint_local": [
                int(endpoint[0]),
                int(endpoint[1]),
            ],
        }

    (
        length,
        _negative_distance,
        component_index,
        endpoint,
        parent_spikelet_index,
        distance,
        path,
    ) = max(candidates)

    return {
        "status": (
            "ok_raster_connected_rooted"
            if len(components) == 1
            else "review_raster_multicomponent_rooted"
        ),
        "path": path,
        "length_px": float(length),
        "vector_part_count": vector_part_count,
        "raster_component_count": len(components),
        "root_raster_component_index": int(component_index),
        "parent_spikelet_index": int(parent_spikelet_index),
        "base_distance_px": float(distance),
        "root_endpoint_local": [
            int(endpoint[0]),
            int(endpoint[1]),
        ],
        "raster_component_pixel_area": int(
            components[component_index].pixel_area
        ),
    }

# Cleaner canonical alias for new callers. Historical callers keep using the old name.
extract_centerline = extract_centerline_multicomponent_v2_rooted


__all__ = [
    "MAX_GAP_PX",
    "MAX_TANGENT_ANGLE_DEG",
    "MAX_CONNECTOR_ANGLE_DEG",
    "MIN_JOIN_SCORE",
    "MIN_COMPONENT_LENGTH_PX",
    "OUTWARD_DISTANCE_TOLERANCE_PX",
    "ROOT_BASE_ENVELOPE_PX",
    "MICRO_GAP_PX",
    "SkeletonComponent",
    "skeleton_component",
    "global_point",
    "rooted_path",
    "nearest_spikelet_root",
    "RasterSkeletonComponent",
    "raster_skeleton_components",
    "raster_global_point",
    "raster_rooted_path",
    "extract_raster_connected_rooted",
    "extract_centerline_multicomponent_v2_rooted",
    "extract_centerline",
]
