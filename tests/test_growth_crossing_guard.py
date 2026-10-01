"""Geometry-only regression fixtures; never publication evidence."""
from pathlib import Path
import sys,math
import numpy as np
import pytest
from shapely.geometry import LineString
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'src/awnphen').is_dir())
sys.path.insert(0,str(ROOT/'src'))
from awnphen.phenotyping.physical.growth.crossing import CrossingGuard,CrossingPolicy,match_pair
from awnphen.phenotyping.physical.orientation import ScaleContext,OrientationTransform
from awnphen.phenotyping.physical.trajectory import path_length
from awnphen.phenotyping.physical.support_integration import resolve_support_path
import awnphen.phenotyping.physical.growth.pipeline as gp
import awnphen.phenotyping.physical.growth.growth as gm
import awnphen.phenotyping.physical.growth.ownership as ow
TRANSFORM=OrientationTransform(ScaleContext(50.,50.,True),0.,False,1.,1.)
def points(vertices):
    out=[]
    for a,b in zip(vertices,vertices[1:]):
        out+=np.linspace(a,b,math.ceil(math.dist(a,b)),endpoint=False).round().tolist()
    return [tuple(p) for p in out]+[tuple(vertices[-1])]
def support(sid,vertices):
    raw=points(vertices);can=[TRANSFORM.raw_px_to_canonical_mm(p) for p in raw]
    return {'support_hypothesis_id':sid,'raw_path':raw,'canonical_path_mm':can,
        'canonical_line':LineString(can),'length_mm':path_length(can),
        'geometry':LineString(vertices).buffer(1.2),'confidence':.9,
        'prediction_keys':(sid,),'path_junctions':[],
        '_path_indices':{tuple(p):i for i,p in enumerate(raw)}}
def vector(deg):
    a=math.radians(deg);return (math.cos(a),math.sin(a))
def arms(angles):return [{'vectors':[vector(a)]*3} for a in angles]
def test_clear_crossing_pairing():
    pair,diag=match_pair(arms([-65,-115,65,115]),CrossingPolicy())
    assert pair=={0:3,3:0,1:2,2:1}
    assert diag['all_scale_pairings_agree']
def test_shallow_but_consistent_pairing():
    pair,diag=match_pair(arms([-87,-93,87,93]),CrossingPolicy())
    assert pair and diag['pairing_margin_deg']<8.
def test_unresolvable_parallel_overlap_is_ambiguous():
    pair,diag=match_pair(arms([-89.5,-90.5,89.5,90.5]),CrossingPolicy())
    assert not pair and diag['reason']=='ambiguous_arm_pairing'
def test_curved_unbranched_support_remains_exact():
    original=support('curve',[(30,100),(35,75),(50,50),(70,35)])
    guard=CrossingGuard();out=guard.prepare([original],TRANSFORM)
    assert not guard.contexts and out[0] is original
def test_wrong_two_ended_masks_are_split_and_correct_exit_is_observed():
    a=support('left',[(30,100),(50,60),(30,20)])
    b=support('right',[(70,100),(50,60),(70,20)])
    signatures=[a['geometry'].wkb,b['geometry'].wkb]
    guard=CrossingGuard();out=guard.prepare([a,b],TRANSFORM)
    assert len(guard.contexts)==1 and guard.contexts[0]['pairing']
    seed=next(s for s in out if s['support_hypothesis_id']=='left_crossarc0')
    wrong=next(s for s in out if s['support_hypothesis_id']=='left_crossarc1')
    correct=next(s for s in out if s['support_hypothesis_id']=='right_crossarc1')
    current=seed['canonical_path_mm']
    bad=resolve_support_path(current,wrong,coverage_aware=True)
    good=resolve_support_path(current,correct,coverage_aware=True)
    assert guard.gate(current,wrong,bad) is None
    routed=guard.gate(current,correct,good)
    assert routed and routed['crossing_splice']
    assert routed['raw_path'][-1]==(70.,20.)
    assert [a['geometry'].wkb,b['geometry'].wkb]==signatures
    for p in routed['raw_path'][:routed['crossing_splice']['inserted_observed_nodes']]:
        local=(round(p[0]-guard.graph_offset[0]),round(p[1]-guard.graph_offset[1]))
        assert local in guard.graph
def test_two_Y_junctions_form_a_compound_crossing():
    a=support('left',[(30,100),(50,65),(50,55),(30,20)])
    b=support('right',[(70,100),(50,65),(50,55),(70,20)])
    guard=CrossingGuard();guard.prepare([a,b],TRANSFORM)
    assert len(guard.contexts)==1 and guard.contexts[0]['pairing']
@pytest.mark.parametrize("foreign_nearby,enabled,expect_clip",[
    (False,True,True),(True,True,False),(False,False,False)])
def test_foreign_body_barrier_preserves_parent_and_near_miss(foreign_nearby,enabled,expect_clip):
    seed=support('seed',[(30,100),(30,80)])
    extension=support('extension',[(30,80),(30,20)])
    current=seed['canonical_path_mm']
    resolved=resolve_support_path(current,extension,coverage_aware=True)
    assert resolved is not None
    x=70 if foreign_nearby else 30
    other=TRANSFORM.raw_px_to_canonical_mm((x,50))
    parent=LineString([current[0],current[-1]]).buffer(.3)
    guard=CrossingGuard(CrossingPolicy(foreign_body_barrier=enabled))
    guard.spikelets=[{'id':'parent','canonical_geometry':parent},
        {'id':'other','canonical_geometry':__import__('shapely.geometry',fromlist=['Point']).Point(other).buffer(.3)}]
    guard.register_seeds({'parent':[seed]})
    outcome=guard.foreign_body_clip(current,extension,resolved)
    assert outcome is not None
    if expect_clip:
        assert outcome['growth_stop_reason']=='foreign_spikelet_body'
        assert outcome['foreign_body_clip']['foreign_spikelet_id']=='other'
        line=LineString(outcome['canonical_path_mm'][outcome['resolved_entry_index']:])
        assert not line.intersects(guard.spikelets[1]['canonical_geometry'])
        assert outcome['raw_path'][-1][1]>50
        assert outcome['crossing_original_claim']['interval'][1]<len(extension['raw_path'])-1
    else:
        assert outcome is resolved


def test_guard_runs_concurrently_without_patching_pipeline_functions():
    from concurrent.futures import ThreadPoolExecutor
    before = (gp.build_support_pool, gp.build_canonical_spikelets,
              gm.resolve_support_path, gm.consumed_claim, ow._append_competing_support)
    def run(crossing):
        guard = CrossingGuard()
        pool = ([support('left',[(30,100),(50,60),(30,20)]),
                 support('right',[(70,100),(50,60),(70,20)])] if crossing else
                [support('curve',[(30,100),(35,75),(50,50),(70,35)])])
        guard.prepare(pool, TRANSFORM)
        return guard, len(guard.contexts)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, flag) for flag in (True, False)]
        results = [f.result() for f in futures]
    assert [count for guard,count in results] == [1,0]
    assert results[0][0].counts is not results[1][0].counts
    after = (gp.build_support_pool, gp.build_canonical_spikelets,
             gm.resolve_support_path, gm.consumed_claim, ow._append_competing_support)
    assert after == before

def test_production_ranker_rejects_wrong_arm_and_accepts_observed_exit():
    guard = CrossingGuard()
    pool = guard.prepare([
        support('left',[(30,100),(50,60),(30,20)]),
        support('right',[(70,100),(50,60),(70,20)]),
    ], TRANSFORM)
    seed = next(row for row in pool if row['support_hypothesis_id']=='left_crossarc0')
    current = seed['canonical_path_mm']
    proposed = gm._wide_rank_next_support(
        current, pool, {seed['support_hypothesis_id']},
        spikelet_id='parent', reserved_owner={}, crossing_guard=guard,
    )
    # The route guard evaluates both exits; existing join gates may still
    # reject this tiny raster fixture. They remain authoritative after routing.
    assert guard.counts['reject_wrong_exit'] > 0
    assert guard.counts['accept_paired_exit'] > 0
    if proposed is not None:
        assert proposed['support_hypothesis_id']=='right_crossarc1'
        assert proposed['raw_path'][-1]==(70.,20.)
        assert proposed['crossing_splice']

def test_crossing_policy_is_default_and_explicit_in_parameters():
    from awnphen.phenotyping.physical.growth.config import DEFAULT_UNIFIED_GROWTH_CONFIG
    policy = DEFAULT_UNIFIED_GROWTH_CONFIG.to_dict()
    assert policy['crossing_guard_enabled'] is True
    assert policy['crossing_policy']['minimum_angular_margin_deg']==3.
    assert policy['crossing_policy']['max_direction_deg']==20.
