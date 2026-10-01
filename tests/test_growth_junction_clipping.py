from types import SimpleNamespace
import math
import pytest
from shapely.geometry import LineString
from awnphen.phenotyping.physical.growth.junctions import (
    support_junctions, clip_at_junction, claims_overlap, claim_groups,
)
from awnphen.phenotyping.physical.growth.growth import _wide_rank_next_support, grow_branch
from awnphen.phenotyping.physical.growth.ownership import grow_competing_branches
from awnphen.phenotyping.inspection.growth import _step_view

SPANS=(1.5,2.0,3.0)

def network():
    path=[(0.,-3.),(0.,-4.),(0.,-5.)]
    path += [(-math.sin(math.radians(65))*i,-5.-math.cos(math.radians(65))*i)
             for i in (1.,2.,3.,4.,5.)]
    return {"support_hypothesis_id":"network","raw_path":path,
            "canonical_path_mm":path,"canonical_line":LineString(path),
            "length_mm":7.,"confidence":.9,"prediction_keys":("same",),
            "path_junctions":[{"raw_point":(0.,-5.),"off_path_reach_mm":2.0}]}

def seed():
    path=[(0.,2.),(0.,1.),(0.,0.),(0.,-1.),(0.,-2.),(0.,-3.)]
    return {"support_hypothesis_id":"seed","spikelet_id":"body",
            "raw_path":path,"canonical_path_mm":path,"length_mm":5.,
            "confidence":.9,"prediction_keys":("same",),"mode":"direct","seed_score":0.}

def resolved(support,entry=0,reverse=False):
    raw=list(reversed(support["raw_path"])) if reverse else support["raw_path"]
    return {"raw_path":raw,"canonical_path_mm":raw,"resolved_entry_index":entry,
            "resolved_extension_mm":5.,"resolved_distal_y_mm":-8.,
            "resolved_suffix_length_mm":7.}

def test_sharp_real_junction_preserves_prefix_and_original_mask_path():
    s=network(); original=list(s["raw_path"])
    result=clip_at_junction(seed()["canonical_path_mm"],s,resolved(s),
                            spans_mm=SPANS,max_turn_deg=55.)
    assert result["raw_path"]==original[:3]
    assert result["growth_stop_reason"]=="ambiguous_junction"
    assert result["junction_clip"]["turn_deg"]==pytest.approx(65.)
    assert s["raw_path"]==original

@pytest.mark.parametrize("kind",["smooth_crossing","short_spur","curve_without_branch"])
def test_nonambiguous_paths_are_unchanged(kind):
    s=network()
    if kind=="smooth_crossing":
        s["raw_path"]=[(0.,float(y)) for y in range(-3,-11,-1)]
        s["canonical_path_mm"]=s["raw_path"]
    elif kind=="short_spur":
        s["path_junctions"][0]["off_path_reach_mm"]=.1
    else:
        s["path_junctions"]=[]
    r=resolved(s)
    assert clip_at_junction(seed()["canonical_path_mm"],s,r,spans_mm=SPANS,max_turn_deg=55.) is r

def test_clipping_handles_reversed_support_and_entry_after_junction():
    s=network()
    r=resolved(s,reverse=True)
    # Already below the junction in reversed direction: no future sharp junction.
    r["resolved_entry_index"]=len(s["raw_path"])-2
    assert clip_at_junction([(0.,-6.),(0.,-5.)],s,r,spans_mm=SPANS,max_turn_deg=55.) is r
    r=resolved(s,entry=4)
    assert clip_at_junction(s["raw_path"][:5],s,r,spans_mm=SPANS,max_turn_deg=55.) is r

def test_substantive_off_path_arm_not_pixel_degree_artifact():
    # Junction graph, .1 mm per pixel. Off-path lower arm reaches 2 mm.
    nodes={(0,y) for y in range(-30,21)}|{(x,0) for x in range(1,31)}
    diameter=[(x,0) for x in range(30,-1,-1)]+[(0,y) for y in range(-1,-31,-1)]
    skeleton={"branch_node_count":4,"nodes":nodes,"offset":(0,0),"path":diameter}
    transform=SimpleNamespace(raw_px_to_canonical_mm=lambda p:(p[0]/10,p[1]/10))
    junctions=support_junctions(skeleton,transform)
    assert len(junctions)==1
    assert junctions[0]["off_path_reach_mm"]>=1.9
    assert math.dist(junctions[0]["raw_point"],(0,0))<=1.

@pytest.mark.parametrize("runner",[grow_branch,grow_competing_branches])
def test_truncated_hop_stops_before_duplicate_outgoing_support(runner):
    s=seed();n=network()
    duplicate={**n,"support_hypothesis_id":"duplicate",
               "raw_path":n["raw_path"][2:],"canonical_path_mm":n["raw_path"][2:],
               "canonical_line":LineString(n["raw_path"][2:]),"path_junctions":[]}
    if runner is grow_branch:
        branch=runner(s,[n,duplicate],set(),{})
    else:
        branch=runner([s],[n,duplicate],set(),{})[0]
    assert branch["growth_hops"]==1
    assert branch["raw_path"][-1]==(0.,-5.)
    assert branch["steps"][0]["growth_stop_reason"]=="ambiguous_junction"
    assert branch["steps"][0]["consumed_claim"]["partial"] is True

def test_partial_ownership_leaves_disjoint_arc_available():
    s=network()
    s["claimed_path_intervals"]=({"interval":(0,2),"partial":True},)
    # A different incoming branch already follows the outgoing diagonal.
    current=[s["raw_path"][3],s["raw_path"][4]]
    result=_wide_rank_next_support(current,[s],set(),spikelet_id="other",
                                    reserved_owner={},branch_prediction_keys=("same",))
    assert result is not None
    assert result["consumed_claim"]["interval"][0]>=4
    assert not claims_overlap(result["consumed_claim"],s["claimed_path_intervals"][0])
    assert _wide_rank_next_support(seed()["raw_path"],[s],set(),spikelet_id="other",
                                  reserved_owner={},branch_prediction_keys=("same",)) is None

def test_partial_claim_groups_allow_shared_endpoint_but_block_shared_arc():
    a={"interval":(0,4),"partial":True,"score":1.}
    b={"interval":(4,9),"partial":False,"score":2.}
    c={"interval":(3,9),"partial":False,"score":3.}
    assert not claims_overlap(a,b)
    assert claims_overlap(a,c)
    assert len(claim_groups([a,b],[]))==2
    assert len(claim_groups([c],[a]))==1
    # Legacy full-support competitors retain their old grouping.
    assert len(claim_groups([b,{"interval":(20,30),"partial":False}],[]))==1

def test_inspection_replays_exact_truncated_path():
    s=seed();n=network();branch=grow_branch(s,[n],set(),{})
    step=branch["steps"][0]
    view=_step_view(step,{"network":n})
    replay=s["raw_path"]+[tuple(p) for p in view["raw_path"][view["entry_index"]:]]
    assert replay==branch["raw_path"]
    assert view["growth_stop_reason"]=="ambiguous_junction"
