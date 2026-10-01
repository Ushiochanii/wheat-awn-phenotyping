"""Root-side normalization for representative awn centerlines.

The operation trims only the contiguous root-side prefix that remains inside the
associated spikelet.  A stable outside hold prevents one-pixel boundary noise
from moving the root, and short paths are protected because root uncertainty is
large relative to the 5 mm biological/measurement threshold.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from shapely import affinity
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry


# Conservative pre-normalization cleanup for long root-side boundary hugs.
def trim_initial_spikelet_boundary_hug(
    path,
    spikelet_geometry,
    grid_period_px: float,
):
    """Trim only a long initial run that hugs the spikelet boundary."""
    pts = np.asarray(path, dtype=float)
    tolerance = float(
        max(1.0, float(grid_period_px) / 60.0)
    )
    if len(pts) < 3:
        return list(path), {
            "applied": False,
            "boundary_run_px": 0.0,
            "trigger_px": float(grid_period_px),
            "boundary_tolerance_px": tolerance,
        }

    boundary = spikelet_geometry.boundary
    near = np.asarray(
        [
            Point(float(x), float(y)).distance(boundary)
            <= tolerance
            for x, y in pts
        ],
        dtype=bool,
    )
    segment_lengths = np.linalg.norm(
        np.diff(pts, axis=0),
        axis=1,
    )

    k = 0
    while (
        k + 1 < len(pts)
        and near[k]
        and near[k + 1]
    ):
        k += 1

    run = (
        float(segment_lengths[:k].sum())
        if k > 0
        else 0.0
    )
    trigger = float(grid_period_px)

    if run < trigger or k >= len(pts) - 2:
        return pts.tolist(), {
            "applied": False,
            "boundary_run_px": run,
            "trigger_px": trigger,
            "boundary_tolerance_px": tolerance,
        }

    trimmed = pts[k:].tolist()
    return trimmed, {
        "applied": True,
        "boundary_run_px": run,
        "trigger_px": trigger,
        "boundary_tolerance_px": tolerance,
        "trimmed_point_count": int(k),
    }


APEX_RESCUE_MIN_DEPTH_MM = 0.60
APEX_RESCUE_MAX_DEPTH_MM = 1.50
APEX_RESCUE_MAX_DISTANCE_MM = 0.30
APEX_RESCUE_MAX_TRIM_MM = 2.00


def calibrated_segment_length_mm(a: Sequence[float], b: Sequence[float], *, x_period_px_5mm: float, y_period_px_5mm: float) -> float:
    sx=5.0/float(x_period_px_5mm); sy=5.0/float(y_period_px_5mm)
    return math.hypot((float(b[0])-float(a[0]))*sx,(float(b[1])-float(a[1]))*sy)


def calibrated_path_length_mm(path: Sequence[Sequence[float]], *, x_period_px_5mm: float, y_period_px_5mm: float) -> float:
    return sum(calibrated_segment_length_mm(a,b,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm) for a,b in zip(path,path[1:]))


def _interp(a,b,t): return (float(a[0])+t*(float(b[0])-float(a[0])),float(a[1])+t*(float(b[1])-float(a[1])))


def _point_at_mm(path,target_mm,*,x_period_px_5mm,y_period_px_5mm):
    pts=[(float(p[0]),float(p[1])) for p in path]
    if target_mm<=0:return pts[0]
    total=0.0
    for a,b in zip(pts,pts[1:]):
        L=calibrated_segment_length_mm(a,b,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
        if total+L>=target_mm and L>1e-12:return _interp(a,b,(target_mm-total)/L)
        total+=L
    return pts[-1]


def _sample(path, step_mm, *, x_period_px_5mm, y_period_px_5mm):
    """Sample increasing arc distances with one forward segment cursor.

    Keep the historical sample distances, sequential sums and interpolation
    arithmetic unchanged. Only the repeated searches from the root disappear.
    """
    pts = [(float(point[0]), float(point[1])) for point in path]
    lengths = [
        calibrated_segment_length_mm(
            a, b,
            x_period_px_5mm=x_period_px_5mm,
            y_period_px_5mm=y_period_px_5mm,
        )
        for a, b in zip(pts, pts[1:])
    ]
    total = sum(lengths)
    index = 0
    prefix = 0.0

    def point_at(distance):
        nonlocal index, prefix
        if distance <= 0:
            return pts[0]
        while index < len(lengths):
            length = lengths[index]
            if prefix + length >= distance and length > 1e-12:
                return _interp(
                    pts[index], pts[index + 1],
                    (distance - prefix) / length,
                )
            prefix += length
            index += 1
        return pts[-1]

    samples = []
    distance = 0.0
    while distance < total - 1e-12:
        samples.append((distance, point_at(distance)))
        distance += step_mm
    samples.append((total, point_at(total)))
    return samples


def _trim_at_mm(path,cut_mm,*,x_period_px_5mm,y_period_px_5mm):
    pts=[(float(p[0]),float(p[1])) for p in path];total=0.0
    for i,(a,b) in enumerate(zip(pts,pts[1:])):
        L=calibrated_segment_length_mm(a,b,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
        if total+L>=cut_mm and L>1e-12:
            return (_interp(a,b,(cut_mm-total)/L),*pts[i+1:])
        total+=L
    return (pts[-1],)


def _distance_mm(
    point: Point,
    geometry: BaseGeometry,
    *,
    x_period_px_5mm: float,
    y_period_px_5mm: float,
) -> float:
    """Return anisotropically calibrated point-to-geometry distance in mm."""
    sx = 5.0 / float(x_period_px_5mm)
    sy = 5.0 / float(y_period_px_5mm)
    point_mm = affinity.scale(point, xfact=sx, yfact=sy, origin=(0.0, 0.0))
    geometry_mm = affinity.scale(
        geometry,
        xfact=sx,
        yfact=sy,
        origin=(0.0, 0.0),
    )
    return float(point_mm.distance(geometry_mm))


def _apex_rescue_shape(
    spikelet_geometry: BaseGeometry,
    root: Point,
    *,
    x_period_px_5mm: float,
    y_period_px_5mm: float,
) -> BaseGeometry | None:
    """Complete a tiny missing spikelet apex only when geometry is compelling."""
    if spikelet_geometry.is_empty:
        return None

    _, min_y, _, _ = spikelet_geometry.bounds
    sy = 5.0 / float(y_period_px_5mm)
    root_depth_mm = (float(root.y) - float(min_y)) * sy
    if not (
        APEX_RESCUE_MIN_DEPTH_MM
        <= root_depth_mm
        <= APEX_RESCUE_MAX_DEPTH_MM
    ):
        return None

    root_distance_mm = _distance_mm(
        root,
        spikelet_geometry,
        x_period_px_5mm=x_period_px_5mm,
        y_period_px_5mm=y_period_px_5mm,
    )
    if root_distance_mm > APEX_RESCUE_MAX_DISTANCE_MM:
        return None

    envelope = spikelet_geometry.minimum_rotated_rectangle
    if envelope.is_empty or not envelope.covers(root):
        return None

    env_min_x, _, env_max_x, _ = envelope.bounds
    apex_depth_px = APEX_RESCUE_MAX_DEPTH_MM / sy
    rescue_zone = envelope.intersection(
        box(env_min_x, min_y, env_max_x, min_y + apex_depth_px)
    )
    if rescue_zone.is_empty or not rescue_zone.covers(root):
        return None
    return spikelet_geometry.union(rescue_zone)


def normalize_root_to_spikelet_exit(
    raw_path: Sequence[Sequence[float]],
    spikelet_geometry: BaseGeometry,
    *,
    x_period_px_5mm: float,
    y_period_px_5mm: float,
    outside_hold_mm: float=0.75,
    sample_step_mm: float=0.10,
    tolerance_px: float=1.0,
    min_path_mm: float=10.0,
) -> tuple[tuple[tuple[float,float],...], Mapping[str,Any]]:
    """Trim a representative path to its first stable exit from the spikelet.

    Only the root-side prefix may be removed. Once the path remains outside for
    ``outside_hold_mm``, later re-contacts with the polygon are ignored. Paths
    shorter than ``min_path_mm`` are left unchanged.
    """
    path=tuple((float(p[0]),float(p[1])) for p in raw_path)
    if len(path)<2:return path,{"status":"too_short","removed_mm":0.0}
    before=calibrated_path_length_mm(path,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
    if before<min_path_mm:return path,{"status":"short_path_guard","removed_mm":0.0,"before_mm":before,"min_path_mm":min_path_mm}
    shape=spikelet_geometry.buffer(tolerance_px)
    root=Point(path[0])
    apex_rescue=False
    if not shape.covers(root):
        rescued=_apex_rescue_shape(
            spikelet_geometry,
            root,
            x_period_px_5mm=x_period_px_5mm,
            y_period_px_5mm=y_period_px_5mm,
        )
        if rescued is None:
            return path,{"status":"root_already_outside","removed_mm":0.0,"root_inside":False}
        shape=rescued.buffer(tolerance_px)
        if not shape.covers(root):
            return path,{"status":"root_already_outside","removed_mm":0.0,"root_inside":False}
        apex_rescue=True
    samples=_sample(path,sample_step_mm,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
    inside=[shape.covers(Point(p)) for _,p in samples]
    candidate=None
    for i in range(1,len(samples)):
        if inside[i]:continue
        d0=samples[i][0];j=i
        while j<len(samples) and samples[j][0]-d0<outside_hold_mm-1e-9:
            if inside[j]:break
            j+=1
        if j>=len(samples):
            if samples[-1][0]-d0>=outside_hold_mm-1e-9 and all(not x for x in inside[i:]):candidate=i;break
        elif samples[j][0]-d0>=outside_hold_mm-1e-9 and all(not x for x in inside[i:j+1]):candidate=i;break
    if candidate is None:return path,{"status":"no_stable_exit","removed_mm":0.0,"root_inside":True}
    prev=candidate-1
    while prev>=0 and not inside[prev]:prev-=1
    if prev<0:return path,{"status":"exit_bracket_unavailable","removed_mm":0.0,"root_inside":True}
    lo,hi=samples[prev][0],samples[candidate][0]
    for _ in range(24):
        mid=(lo+hi)/2
        p=_point_at_mm(path,mid,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
        if shape.covers(Point(p)):lo=mid
        else:hi=mid
    trimmed=_trim_at_mm(path,hi,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
    after=calibrated_path_length_mm(trimmed,x_period_px_5mm=x_period_px_5mm,y_period_px_5mm=y_period_px_5mm)
    removed=before-after
    if apex_rescue and removed>APEX_RESCUE_MAX_TRIM_MM:
        return path,{
            "status":"root_already_outside",
            "removed_mm":0.0,
            "root_inside":False,
            "apex_rescue_attempted":True,
            "apex_rescue_rejected":"trim_too_long",
            "apex_rescue_candidate_trim_mm":removed,
        }
    return trimmed,{
        "status":(
            "trimmed_to_stable_spikelet_exit_apex_rescue"
            if apex_rescue
            else "trimmed_to_stable_spikelet_exit"
        ),
        "root_inside":True,
        "removed_mm":removed,
        "cut_mm":hi,
        "before_mm":before,
        "after_mm":after,
        "outside_hold_mm":outside_hold_mm,
        "sample_step_mm":sample_step_mm,
        "tolerance_px":tolerance_px,
        "min_path_mm":min_path_mm,
        **({"apex_rescue":True} if apex_rescue else {}),
    }


__all__=["trim_initial_spikelet_boundary_hug","normalize_root_to_spikelet_exit","calibrated_path_length_mm"]
