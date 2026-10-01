import test from 'node:test';
import assert from 'node:assert/strict';
import {
  assessAutomaticReview,
  effectiveReviewStatus
} from '../../app/awn_studio/review_triage.mjs';

test('clean automatic reconstruction stays high confidence', () => {
  const review = assessAutomaticReview({
    winner_seed:{confidence:0.78},
    winner:{
      branch_score:40,
      final_length_mm:42,
      growth_hops:1,
      ownership_events:[]
    },
    steps:[{
      support_confidence:0.72,
      distance_mm:0.22,
      join_local_turn_deg:7,
      join_excess_turn_deg:1
    }],
    alternatives:[{branch_score:34,final_length_mm:39}]
  }, {policy:'spikelet_axis_anchored'});
  assert.equal(review.status,'automatic');
  assert.deepEqual(review.reasons,[]);
});

test('ambiguous reconstruction is flagged with concrete review reasons', () => {
  const review = assessAutomaticReview({
    winner_seed:{confidence:0.30},
    winner:{
      branch_score:50,
      final_length_mm:40,
      growth_hops:3,
      ownership_events:[{result:'shared'}]
    },
    steps:[{
      support_confidence:0.28,
      distance_mm:1.2,
      join_local_turn_deg:19,
      join_excess_turn_deg:7
    }],
    alternatives:[{branch_score:49,final_length_mm:31}]
  }, {policy:'spikelet_axis_anchored'});
  assert.equal(review.status,'needs_review');
  for (const reason of [
    'low_support_confidence',
    'ownership_competition',
    'large_fragment_gap',
    'sharp_join',
    'long_reconstruction_chain',
    'branch_disagreement'
  ]) assert.ok(review.reasons.includes(reason));
});

test('single-spikelet default polarity is reviewable even when the path itself is clean', () => {
  const review = assessAutomaticReview({
    winner_seed:{confidence:0.8},
    winner:{branch_score:30,final_length_mm:30,growth_hops:0,ownership_events:[]},
    steps:[],
    alternatives:[]
  }, {policy:'single_spikelet_default_polarity'});
  assert.equal(review.status,'needs_review');
  assert.ok(review.reasons.includes('degraded_orientation'));
});

test('user provenance overrides automatic triage in the final displayed status', () => {
  const base={line:[[0,0],[0,10]],autoReviewStatus:'needs_review'};
  assert.equal(effectiveReviewStatus(base),'needs_review');
  assert.equal(effectiveReviewStatus({...base,confirmed:true}),'confirmed');
  assert.equal(effectiveReviewStatus({...base,confirmed:true,modified:true}),'modified');
  assert.equal(effectiveReviewStatus({...base,line:[],modified:true}),'missing');
});
