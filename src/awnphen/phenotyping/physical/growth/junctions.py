"""Clip only sharp turns at substantive skeleton junctions during a HOP.

The mask and diameter path remain immutable. This guard is not a graph search:
it can stop an ambiguous continuation but cannot recover an unobserved branch.
"""
from __future__ import annotations

import math
import statistics

from awnphen.core.geometry.skeleton import NEIGHBORS
from awnphen.phenotyping.physical.trajectory import (
    angle_deg, path_length, distal_tangent, continuation_tangent, max_local_turn,
)


def support_junctions(skeleton, transform):
    """Locate diameter junctions with an off-path arm, ignoring pixel stubs.

    Arm reach is measured in canonical mm. The caller compares it with an
    existing tangent span; adjacent raster branch pixels are clustered.
    """
    if not skeleton.get("branch_node_count"):
        return []
    offset = skeleton["offset"]
    nodes = skeleton["nodes"]
    path_nodes = {(round(x-offset[0]), round(y-offset[1])) for x,y in skeleton["path"]}
    off_path = nodes - path_nodes
    components = []
    while off_path:
        start = min(off_path); off_path.remove(start)
        component = {start}; queue = [start]
        while queue:
            x,y = queue.pop()
            for dx,dy,_ in NEIGHBORS:
                point = (x+dx,y+dy)
                if point in off_path:
                    off_path.remove(point);component.add(point);queue.append(point)
        components.append(component)
    out = []
    for component in components:
        attachments = set()
        for x,y in component:
            attachments.update((x+dx,y+dy) for dx,dy,_ in NEIGHBORS
                               if (x+dx,y+dy) in path_nodes)
        if not attachments:
            continue
        raw_center = (sum(p[0] for p in attachments)/len(attachments)+offset[0],
                      sum(p[1] for p in attachments)/len(attachments)+offset[1])
        raw_point = min(skeleton["path"],key=lambda p:math.dist(p,raw_center))
        center = transform.raw_px_to_canonical_mm(raw_point)
        reach = max(math.dist(center,transform.raw_px_to_canonical_mm(
                    (p[0]+offset[0],p[1]+offset[1]))) for p in component)
        out.append({"raw_point":tuple(raw_point),"off_path_reach_mm":float(reach)})
    return sorted(out,key=lambda row:row["raw_point"])


def _point_at_arc(path,index,direction,span):
    origin = path[index]; distance = 0.0
    while 0 <= index+direction < len(path):
        next_point = path[index+direction]
        step = math.dist(path[index],next_point)
        if distance+step >= span and step > 0:
            t = (span-distance)/step
            return tuple(path[index][j]+t*(next_point[j]-path[index][j]) for j in (0,1)),span
        distance += step; index += direction
    return path[index],distance


def clip_at_junction(current_can,support,resolved,*,spans_mm,max_turn_deg):
    """Return a shortened resolved path, or the original unchanged object."""
    junctions = support.get("path_junctions") or ()
    if not junctions:
        return resolved
    raw = resolved["raw_path"];can = resolved["canonical_path_mm"]
    entry = int(resolved["resolved_entry_index"])
    # Junction lookup is exact on the pixel skeleton, including reversed paths.
    indices = {tuple(p):i for i,p in enumerate(raw)}
    eligible = sorted((indices[tuple(j["raw_point"])],j) for j in junctions
                      if tuple(j["raw_point"]) in indices
                      and indices[tuple(j["raw_point"])] >= entry
                      and j["off_path_reach_mm"] >= min(spans_mm))
    for index,junction in eligible:
        if index >= len(raw)-1:
            continue
        incoming_path = list(current_can)+list(can[entry:index+1])
        pivot = can[index]
        angles = []
        for span in spans_mm:
            before,before_span = _point_at_arc(incoming_path,len(incoming_path)-1,-1,span)
            after,after_span = _point_at_arc(can,index,1,span)
            # Do not classify a junction from a one-pixel tangent.
            if min(before_span,after_span) < min(spans_mm):
                continue
            angle = angle_deg((pivot[0]-before[0],pivot[1]-before[1]),
                              (after[0]-pivot[0],after[1]-pivot[1]))
            if angle is not None:
                angles.append({"span_mm":span,"angle_deg":angle})
        if not angles or statistics.median(a["angle_deg"] for a in angles) <= max_turn_deg:
            continue
        # A sharp turn exists at a real branch, not merely somewhere on a curve.
        # Reject a zero-length prefix; no connection to the outgoing arm is made.
        if index <= entry:
            return None
        suffix = can[entry:index+1]
        incoming = distal_tangent(current_can)
        outgoing, _ = continuation_tangent(suffix, suffix[0])
        prefix_angle = angle_deg(incoming, outgoing) if incoming and outgoing else None
        return {**resolved,
                "resolved_angle_deg": prefix_angle,
                "resolved_max_internal_turn_deg": max_local_turn(suffix, span=2.0),
                "raw_path":list(raw[:index+1]),
                "canonical_path_mm":list(can[:index+1]),
                "resolved_extension_mm":float(current_can[-1][1]-min(p[1] for p in suffix)),
                "resolved_distal_y_mm":float(min(p[1] for p in suffix)),
                "resolved_suffix_length_mm":float(path_length(suffix)),
                "junction_clip":{"raw_point":list(raw[index]),"end_index":index,
                                 "turn_deg":float(statistics.median(a["angle_deg"] for a in angles)),
                                 "angles":angles,"off_path_reach_mm":junction["off_path_reach_mm"]},
                "growth_stop_reason":"ambiguous_junction"}
    return resolved


def consumed_claim(support,resolved):
    """Inclusive original-path interval; a shared endpoint is not shared arc."""
    if resolved.get("crossing_original_claim"):
        return {**resolved["crossing_original_claim"], "partial": True}
    lookup = support.get("_path_indices")
    if lookup is None:
        lookup = {tuple(p):i for i,p in enumerate(support["raw_path"])}
    entry = int(resolved["resolved_entry_index"])
    start = lookup[tuple(resolved["raw_path"][entry])]
    end = lookup[tuple(resolved["raw_path"][-1])]
    return {"interval":(min(start,end),max(start,end)),
            "partial":bool(resolved.get("junction_clip"))}


def claims_overlap(left,right):
    # Preserve legacy whole-support competition unless a truncated claim exists.
    if not (left.get("partial") or right.get("partial")):
        return True
    a = left.get("interval");b = right.get("interval")
    if a is None or b is None:
        return True
    return min(a[1],b[1]) > max(a[0],b[0])


def claim_groups(current,prior):
    """Partition proposals only when a partial claim makes arcs disjoint."""
    pending = [(False,r) for r in current]+[(True,r) for r in prior]
    groups = []
    while pending:
        group = [pending.pop(0)]
        changed = True
        while changed:
            changed = False
            for item in list(pending):
                if any(claims_overlap(item[1],member[1]) for member in group):
                    group.append(item);pending.remove(item);changed=True
        now = [r for is_prior,r in group if not is_prior]
        if now:
            groups.append((now,[r for is_prior,r in group if is_prior]))
    return groups
