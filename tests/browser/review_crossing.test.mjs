import test from 'node:test';
import assert from 'node:assert/strict';
import {assessAutomaticReview, reviewReasonLabels} from '../../app/awn_studio/review_triage.mjs';
test('Unresolved crossing endpoint requires review', () => {
  const result=assessAutomaticReview({representative:{review_reason:'crossing_continuation_unresolved',endpoint_status:'unresolved'}});
  assert.equal(result.status,'needs_review');
  assert.deepEqual(result.reasons,['crossing_continuation_unresolved']);
  assert.equal(result.signals.endpoint_status,'unresolved');
  assert.equal(reviewReasonLabels({reviewReasons:result.reasons})[0],'The awn continuation at a crossing requires review');
});
test('Foreign-body stop requires review and preserves other diagnostics', () => {
  const result=assessAutomaticReview({representative:{review_reason:'foreign_spikelet_body',endpoint_status:'unresolved'}},{orientation_degraded:true});
  assert.deepEqual(result.reasons,['degraded_orientation','foreign_spikelet_body']);
});
