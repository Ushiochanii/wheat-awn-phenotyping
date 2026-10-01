"""Page-local crossing context from combined masks, without image or GT access.
Individual two-ended masks can already switch awns. Cut support trajectories at
substantive combined-silhouette junctions and enforce paired incoming/outgoing arms.
The model evidence and mask geometries are immutable. No global pipeline hooks.
"""
from collections import Counter
from dataclasses import asdict,dataclass
import hashlib,math,statistics,time,heapq
import cv2
import numpy as np
from skimage.morphology import skeletonize
from shapely.geometry import LineString,Point,MultiPoint
from shapely import contains_xy
from shapely.ops import unary_union
from shapely.strtree import STRtree
from awnphen.core.geometry.skeleton import rasterize,NEIGHBORS
from awnphen.phenotyping.physical.trajectory import (
    _pca_direction,angle_deg,path_length,distal_tangent)
from awnphen.phenotyping.physical.support_integration import _resolved_path_candidate

@dataclass(frozen=True)
class CrossingPolicy:
    spans_mm:tuple=(1.5,2.0,3.0)
    min_arm_mm:float=1.5
    junction_cluster_radius_mm:float=.20
    crossing_radius_mm:float=.60
    gate_radius_mm:float=.90
    max_direction_deg:float=20.
    ambiguity_margin_deg:float=8.
    minimum_angular_margin_deg:float=3.
    foreign_body_barrier:bool=True
    root_exclusion_mm:float=2.8

def direction(path,span):
    if len(path)<2:return None
    length=0.;out=[path[0]]
    for a,b in zip(path,path[1:]):
        out.append(b);length+=math.dist(a,b)
        if length>=span:break
    fitted=_pca_direction(out)
    return None if fitted is None else fitted[0]
def vectors(path,spans):return [direction(path,span) for span in spans]
def mismatch(left,right,reverse=False):
    values=[angle_deg((-a[0],-a[1]) if reverse else a,b)
        for a,b in zip(left,right) if a is not None and b is not None]
    return statistics.median(values) if values else 999.
def match_pair(arms,policy):
    if len(arms)!=4:return {},{'reason':'not_four_substantial_arms'}
    pairings=[[(0,1),(2,3)],[(0,2),(1,3)],[(0,3),(1,2)]]
    ranked=[]
    for pairs in pairings:
        costs=[mismatch(arms[a]['vectors'],arms[b]['vectors'],True) for a,b in pairs]
        ranked.append((sum(costs)/2,max(costs),pairs,costs))
    ranked.sort()
    best=ranked[0];margin=ranked[1][0]-best[0]
    # Require agreement at every existing tangent scale. A fixed8-degree gap
    # over-rejects shallow X crossings even when all scale estimates agree.
    uncertainty=max((angle_deg(a,b) or 0.) for arm in arms
        for a in arm['vectors'] if a is not None for b in arm['vectors'] if b is not None)
    required_margin=max(policy.minimum_angular_margin_deg,uncertainty)
    scale_choices=[]
    for scale_index in range(len(policy.spans_mm)):
        alternatives=[]
        for pairs in pairings:
            costs=[]
            for a,b in pairs:
                va=arms[a]['vectors'][scale_index];vb=arms[b]['vectors'][scale_index]
                costs.append(999. if va is None or vb is None else angle_deg((-va[0],-va[1]),vb))
            alternatives.append((sum(costs)/2,pairs))
        alternatives.sort();scale_choices.append(alternatives[0][1]==best[2])
    if best[1]>policy.max_direction_deg or margin<required_margin or not all(scale_choices):
        return {},{'reason':'ambiguous_arm_pairing','best_mean_turn_deg':best[0],
            'best_max_turn_deg':best[1],'pairing_margin_deg':margin,
            'required_margin_deg':required_margin,'all_scale_pairings_agree':all(scale_choices)}
    pairs={}
    for a,b in best[2]:pairs[a]=b;pairs[b]=a
    return pairs,{'reason':'paired','best_mean_turn_deg':best[0],
        'best_max_turn_deg':best[1],'pairing_margin_deg':margin,
        'required_margin_deg':required_margin,'all_scale_pairings_agree':True}

class CrossingGuard:
    def __init__(self,policy=None):
        self.policy=policy or CrossingPolicy();self.contexts=[];self.counts=Counter()
        self.events=[];self.tip_cache={};self.pool=[];self.spikelets=[];self.accepted_stops=[]
    def prepare(self,pool,transform):
        self.transform=transform;self.input_pool=pool
        started=time.perf_counter()
        if not pool:self.pool=[];return []
        mask,offset=rasterize(unary_union([s['geometry'] for s in pool]))
        skeleton=skeletonize(mask>0)
        ys,xs=np.where(skeleton);nodes=set(zip(xs.tolist(),ys.tolist()))
        adj={}
        for x,y in sorted(nodes):
            neighbors=[]
            for dx,dy,_ in NEIGHBORS:
                q=(x+dx,y+dy)
                if q not in nodes:continue
                # Suppress diagonal triangle shortcuts when a cardinal edge exists.
                if dx and dy and ((x+dx,y) in nodes or (x,y+dy) in nodes):continue
                neighbors.append(q)
            adj[(x,y)]=neighbors
        self.graph=adj;self.graph_offset=offset
        high=[p for p,a in adj.items() if len(a)>2]
        critical=np.zeros_like(mask)
        for x,y in high:critical[y,x]=1
        scale=min(transform.scale.x_mm_per_px,transform.scale.y_mm_per_px)
        radius=max(1,round(self.policy.junction_cluster_radius_mm/scale))
        zone_mask=cv2.dilate(critical,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*radius+1,2*radius+1)))>0
        zones={p for p in nodes if zone_mask[p[1],p[0]]}
        groups=[];unseen=set(zones)
        while unseen:
            root=min(unseen);unseen.remove(root);group={root};queue=[root]
            while queue:
                p=queue.pop()
                for q in adj[p]:
                    if q in unseen:unseen.remove(q);group.add(q);queue.append(q)
            if any(p in group for p in high):groups.append(group)
        # A shallow crossing rasterizes as two Y junctions connected by a shared
        # stem, rather than a single four-way node. Pair those compound junctions.
        owner={p:i for i,g in enumerate(groups) for p in g}
        links={}
        for i,group in enumerate(groups):
            for a in sorted(group):
                for b in adj[a]:
                    if b in group:continue
                    previous,point=a,b;trail=[a,b];seen={a,b};distance=0.
                    while True:
                        if point in owner:
                            j=owner[point]
                            if j!=i:
                                key=tuple(sorted((i,j)))
                                links.setdefault(key,[]).append((distance,list(trail)))
                            break
                        options=[q for q in adj[point] if q!=previous and q not in seen]
                        if len(options)!=1:break
                        q=options[0];seen.add(q);trail.append(q)
                        distance+=math.hypot(q[0]-point[0],q[1]-point[1])*scale
                        previous,point=point,q
                        if distance>3*max(self.policy.spans_mm):break
        consumed=set();compound=[]
        for (i,j),trails in sorted(links.items(),key=lambda kv:min(t[0] for t in kv[1])):
            if i in consumed or j in consumed:continue
            distance,trail=min(trails)
            merged=groups[i]|groups[j]|set(trail)
            exits={(p,q) for p in merged for q in adj[p] if q not in merged}
            if len(exits)!=4:continue
            compound.append(merged);consumed.update((i,j))
        groups=compound+[g for i,g in enumerate(groups) if i not in consumed]
        allzones=set().union(*groups) if groups else set()
        def raw(point):return (float(point[0]+offset[0]),float(point[1]+offset[1]))
        for group in groups:
            rawcenter=(sum(p[0] for p in group)/len(group)+offset[0],
                sum(p[1] for p in group)/len(group)+offset[1])
            cancenter=transform.raw_px_to_canonical_mm(rawcenter)
            if any(Point(cancenter).distance(s['canonical_geometry'])<self.policy.root_exclusion_mm for s in self.spikelets):continue
            exits=sorted((p,q) for p in group for q in adj[p] if q not in group)
            arms=[];seen_exits=set()
            for a,b in exits:
                if b in seen_exits:continue
                sequence=[raw(a),raw(b)];can=[transform.raw_px_to_canonical_mm(p) for p in sequence]
                previous,point=a,b;visited={a,b};length=math.dist(can[0],can[1])
                while length<max(self.policy.spans_mm)+.5:
                    if point in allzones:break
                    choices=[q for q in adj[point] if q!=previous and q not in visited]
                    if len(choices)!=1:break
                    following=choices[0];visited.add(following)
                    next_raw=raw(following);next_can=transform.raw_px_to_canonical_mm(next_raw)
                    length+=math.dist(can[-1],next_can);sequence.append(next_raw);can.append(next_can)
                    previous,point=point,following
                seen_exits.update(visited-group)
                if length<self.policy.min_arm_mm:continue
                arms.append({'raw_path':sequence,'canonical_path':can,'vectors':vectors(can,self.policy.spans_mm),'length_mm':length})
            if len(arms)!=4:continue
            pairing,diagnostic=match_pair(arms,self.policy)
            identifier='cross_'+hashlib.sha256(repr(tuple(sorted(group))).encode()).hexdigest()[:12]
            self.contexts.append({'id':identifier,'raw_point':rawcenter,'canonical_point':cancenter,
                'arms':arms,'pairing':pairing,'diagnostic':diagnostic,
                '_core':MultiPoint([transform.raw_px_to_canonical_mm(raw(p)) for p in group]).convex_hull.buffer(self.policy.crossing_radius_mm),
                '_allowed_nodes':set(group)|{(round(p[0]-offset[0]),round(p[1]-offset[1])) for a in arms for p in a['raw_path']}})
        self.tree=STRtree([c['_core'] for c in self.contexts])
        self.pool=self.split_supports(pool)
        self.counts.update(contexts=len(self.contexts),paired_contexts=sum(bool(c['pairing']) for c in self.contexts),
            old_supports=len(pool),new_supports=len(self.pool))
        self.prepare_seconds=time.perf_counter()-started
        return self.pool
    def contexts_near(self,point,radius):
        return [self.contexts[int(i)] for i in self.tree.query(Point(point).buffer(radius))] if self.contexts else []
    def split_supports(self,pool):
        result=[]
        for support in pool:
            raw=support['raw_path'];can=support['canonical_path_mm']
            line=support['canonical_line'];cuts=[]
            for i in self.tree.query(line):
                context=self.contexts[int(i)];arr=np.asarray(can)
                inside=np.flatnonzero(contains_xy(context['_core'],arr[:,0],arr[:,1]))
                if len(inside):
                    index=int(inside[0])
                    if 1<index<len(can)-2:cuts.append((index,context['id']))
            if not cuts:result.append(support);continue
            indices=sorted({0,len(raw)-1,*[i for i,c in cuts]})
            for number,(start,end) in enumerate(zip(indices,indices[1:])):
                if end-start<2:continue
                segment=list(raw[start:end+1]);canonical=list(can[start:end+1])
                row={**support,'support_hypothesis_id':support['support_hypothesis_id']+f'_crossarc{number}',
                    'parent_support_hypothesis_id':support['support_hypothesis_id'],
                    'raw_path':segment,'canonical_path_mm':canonical,'canonical_line':LineString(canonical),
                    'length_mm':path_length(canonical),'_path_indices':{tuple(p):j for j,p in enumerate(segment)},
                    'path_junctions':[j for j in support.get('path_junctions',[]) if tuple(j['raw_point']) in set(segment)],
                    'crossing_split':{'parent_interval':[start,end],'context_ids':[c for i,c in cuts]}}
                result.append(row)
        return result
    def event(self,reason,context,support,current,**extra):
        self.counts[reason]+=1
        if len(self.events)<120:self.events.append({'reason':reason,'context':context['id'],
            'support_id':support['support_hypothesis_id'],'current_root_mm':list(current[0]),
            'current_tip_mm':list(current[-1]),**extra})
    def gate(self,current,support,resolved):
        if resolved is None or not self.contexts:return resolved
        entry=int(resolved['resolved_entry_index']);suffix=resolved['canonical_path_mm'][entry:]
        if len(suffix)<2:return resolved
        tip=tuple(current[-1])
        if tip not in self.tip_cache:self.tip_cache[tip]=self.contexts_near(tip,self.policy.gate_radius_mm)
        contexts={c['id']:c for c in self.tip_cache[tip]}
        contexts.update({self.contexts[int(i)]['id']:self.contexts[int(i)] for i in self.tree.query(LineString(suffix))})
        combined=list(current)+list(suffix);coordinates=np.asarray(combined)
        for context in contexts.values():
            indices=np.flatnonzero(contains_xy(context['_core'],coordinates[:,0],coordinates[:,1]))
            if not len(indices):continue
            first,last=int(indices[0]),int(indices[-1])
            before=combined[:first+1];after=combined[last:]
            if first<2 or last>=len(combined)-2:
                self.event('reject_incomplete_crossing',context,support,current);return None
            incoming=[distal_tangent(before,trim_mm=.5,span_mm=span) for span in self.policy.spans_mm]
            outgoing=vectors(after,self.policy.spans_mm)
            if not context['pairing']:
                self.event('reject_ambiguous_crossing',context,support,current);return None
            arms=context['arms']
            entering=sorted((mismatch(incoming,a['vectors'],True),j) for j,a in enumerate(arms))
            leaving=sorted((mismatch(outgoing,a['vectors']),j) for j,a in enumerate(arms))
            if entering[0][0]>self.policy.max_direction_deg or entering[1][0]-entering[0][0]<context['diagnostic'].get('required_margin_deg',self.policy.ambiguity_margin_deg):
                self.event('reject_ambiguous_entry',context,support,current);return None
            expected=context['pairing'][entering[0][1]]
            if leaving[0][0]>self.policy.max_direction_deg or leaving[0][1]!=expected:
                self.event('reject_wrong_exit',context,support,current,
                    incoming_arm=entering[0][1],expected_arm=expected,proposed_arm=leaving[0][1],
                    incoming_angle=entering[0][0],outgoing_angle=leaving[0][0]);return None
            self.event('accept_paired_exit',context,support,current,
                incoming_arm=entering[0][1],outgoing_arm=expected)
            resolved=self.splice_core(current,support,resolved,context)
            if resolved is None:return None
        return resolved
    def register_seeds(self,groups):
        self.root_parents={tuple(seed['canonical_path_mm'][0]):sid for sid,seeds in groups.items() for seed in seeds}
        self.body_tree=STRtree([s['canonical_geometry'] for s in self.spikelets])
    def foreign_body_clip(self,current,support,resolved):
        if resolved is None or not self.policy.foreign_body_barrier:return resolved
        parent=getattr(self,'root_parents',{}).get(tuple(current[0]))
        if parent is None:return resolved
        entry=int(resolved['resolved_entry_index']);can=list(resolved['canonical_path_mm'])
        suffix=can[entry:]
        if len(suffix)<2:return resolved
        line=LineString(suffix);first=None
        for i in self.body_tree.query(line,predicate='intersects'):
            body=self.spikelets[int(i)]
            if body['id']==parent:continue
            intersection=line.intersection(body['canonical_geometry'])
            pieces=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
            for piece in pieces:
                points=list(piece.coords) if hasattr(piece,'coords') else []
                for p in points:
                    arc=float(line.project(Point(p)))
                    if first is None or arc<first[0]:first=(arc,body['id'])
        if first is None:return resolved
        cumulative=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.asarray(suffix),axis=0),axis=1))]
        before=np.flatnonzero(cumulative<first[0]-.05)
        if len(before)<2:return None
        end=entry+int(before[-1])
        raw=list(resolved['raw_path'][:end+1]);can=can[:end+1]
        from awnphen.phenotyping.physical.growth.junctions import consumed_claim
        claim=resolved.get('crossing_original_claim') or consumed_claim(support,resolved)
        lookup=support.get('_path_indices',{})
        if tuple(raw[-1]) in lookup:
            claim={**claim,'interval':(claim['interval'][0],lookup[tuple(raw[-1])])}
        subset=can[entry:];candidate=_resolved_path_candidate(current,raw,can)
        if candidate is None:return None
        stop={'foreign_spikelet_id':first[1],'raw_endpoint':list(raw[-1])}
        self.counts['foreign_body_clip_proposals']+=1
        return {**resolved,**candidate,'crossing_original_claim':claim,
            'foreign_body_clip':stop,'growth_stop_reason':'foreign_spikelet_body'}
    def splice_core(self,current,support,resolved,context):
        """Traverse observed union skeleton inside the crossing; preserve native exit.
        This avoids joining sideways between two offset raster tracks in an overlap.
        Every inserted node belongs to the unmodified union of real model masks.
        """
        entry=int(resolved['resolved_entry_index'])
        suffix=list(resolved['canonical_path_mm'][entry:]);raw_suffix=list(resolved['raw_path'][entry:])
        array=np.asarray(suffix);inside=np.flatnonzero(contains_xy(context['_core'],array[:,0],array[:,1]))
        if not len(inside):return resolved
        exit_index=int(inside[-1])+1
        if exit_index>=len(suffix)-1:return None
        rawtip=self.transform.canonical_mm_to_raw_px(current[-1])
        allowed=context['_allowed_nodes'];offset=self.graph_offset
        def near(raw):
            return min(allowed,key=lambda p:math.dist((p[0]+offset[0],p[1]+offset[1]),raw))
        start=near(rawtip);end=near(raw_suffix[exit_index])
        previous={};distances={start:0.};queue=[(0.,start)]
        while queue:
            distance,point=heapq.heappop(queue)
            if distance!=distances.get(point):continue
            if point==end:break
            for following in self.graph[point]:
                if following not in allowed:continue
                value=distance+math.dist(point,following)
                if value<distances.get(following,float('inf')):
                    distances[following]=value;previous[following]=point;heapq.heappush(queue,(value,following))
        if end not in distances:return None
        nodes=[end]
        while nodes[-1]!=start:nodes.append(previous[nodes[-1]])
        nodes.reverse()
        raw=[(float(p[0]+offset[0]),float(p[1]+offset[1])) for p in nodes]+raw_suffix[exit_index:]
        can=[self.transform.raw_px_to_canonical_mm(p) for p in raw]
        candidate=_resolved_path_candidate(current,raw,can)
        if candidate is None:return None
        from awnphen.phenotyping.physical.growth.junctions import consumed_claim
        original_claim=resolved.get('crossing_original_claim') or consumed_claim(support,resolved)
        self.counts['observed_core_splices']+=1
        return {**resolved,**candidate,'crossing_original_claim':original_claim,
            'crossing_splice':{'context_id':context['id'],'inserted_observed_nodes':len(nodes)},
            'resolution_source':'observed_crossing_union'}
    def manifest(self):
        return {'policy':asdict(self.policy),'counts':dict(self.counts),'prepare_seconds':getattr(self,'prepare_seconds',0),
            'contexts':[{**{k:v for k,v in c.items() if not k.startswith('_')},'core_wkt_mm':c['_core'].wkt} for c in self.contexts],
            'sample_gate_events':self.events,'accepted_foreign_body_stops':getattr(self,'accepted_stops',[]),
            'evidence_geometry_modified':False}


    def record_growth(self, growth):
        """Keep accepted-stop diagnostics without intercepting ownership functions."""
        self.accepted_stops = [
            {"spikelet_id": row["spikelet_id"], "seed_id": branch["seed_hypothesis_id"],
             **step["foreign_body_clip"]}
            for row in growth for branch in row.get("_branches", ())
            for step in branch.get("steps", ()) if step.get("foreign_body_clip")
        ]

    def endpoint_review_reason(self, representative):
        """A stop at a crossing is unresolved, not evidence of a physical awn tip."""
        path = representative.get("canonical_path_mm") or ()
        if not path:
            return None
        point = Point(path[-1])
        if self.contexts and any(c["_core"].covers(point) for c in self.contexts_near(path[-1], self.policy.gate_radius_mm)):
            return "crossing_continuation_unresolved"
        return None


def run_guarded_page(evidence, page, *, calibration, inspection_sink=None, policy=None):
    """Explicit reusable guard runner; production defaults use the same implementation."""
    from .pipeline import run_unified_growth_page
    guard = CrossingGuard(policy)
    result = run_unified_growth_page(
        evidence, page, calibration=calibration,
        inspection_sink=inspection_sink, crossing_guard=guard,
    )
    return result, guard


__all__ = ["CrossingPolicy", "CrossingGuard", "match_pair", "run_guarded_page"]
