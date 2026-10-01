import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PRODUCT_RESULT_SCHEMA,
  normalizeProductResult,
  editableGroupsFromProductResult,
  inspectionRecordForSpikelet,
  displayLayersFromProductResult,
  resultSummary
} from '../../app/awn_studio/contracts.mjs';

test('legacy inference result is normalized into the product contract', () => {
  const legacy = {
    groups: [{
      uid: 'spikelet-1',
      name: '1',
      polygon: [[0,0],[10,0],[10,20],[0,20]],
      line: [[5,0],[5,-10]],
      origin: 'automatic',
      modified: false,
      confirmed: false,
      modelAwnId: 'awn-7'
    }],
    layers: {
      raw: [{id:'raw-1'}],
      candidates: [{id:'candidate-1'}],
      representatives: [{id:'representative-1'}]
    },
    model: 'example-model',
    model_id: 'example-model-id',
    weights_sha256: 'abc',
    pipeline: 'awnphen physical closeout',
    pipeline_stages: ['evidence','reconstruction'],
    orientation: {rotation_deg:270,polarity_flipped:true,policy:'spikelet_axis_anchored'},
    device: 'cpu',
    seconds: 12.5,
    path_count: 1,
    source_sha256: 'source',
    inspection: {
      schema:'unified_growth_inspection_v1',
      stages:['source','trajectory_growth'],
      support_pool:[{support_hypothesis_id:'support-1',raw_path:[[1,1],[2,2]]}],
      source_to_product_spikelet:{'source-spikelet-1':'spikelet-1'},
      records:{
        'spikelet-1':{
          spikelet_id:'spikelet-1',
          source_spikelet_id:'source-spikelet-1',
          steps:[{hop:1,support_hypothesis_id:'support-1',raw_path:[[1,1],[2,2]]}]
        }
      }
    }
  };

  const result = normalizeProductResult(legacy);
  assert.equal(result.schema, PRODUCT_RESULT_SCHEMA);
  assert.equal(result.measurements.length, 1);
  assert.equal(result.measurements[0].spikelet.id, 'spikelet-1');
  assert.equal(result.measurements[0].representative_awn.id, 'awn-7');
  assert.deepEqual(result.measurements[0].representative_awn.measurement_path, [[5,0],[5,-10]]);
  assert.equal(result.run.model.id, 'example-model-id');
  assert.equal(result.run.model.name, 'example-model');
  assert.equal(result.run.duration_seconds, 12.5);
  assert.deepEqual(result.run.orientation, {rotation_deg:270,polarity_flipped:true,policy:'spikelet_axis_anchored'});
  assert.equal(result.compatibility.source_schema, 'legacy-workbench-result');
  assert.equal(result.inspection.schema, 'unified_growth_inspection_v1');
  assert.deepEqual(result.inspection.stages, ['source','trajectory_growth']);
  assert.equal(result.inspection.records['spikelet-1'].steps[0].support_hypothesis_id, 'support-1');
  assert.equal(result.inspection.source_to_product_spikelet['source-spikelet-1'], 'spikelet-1');
  assert.equal(inspectionRecordForSpikelet(result,'spikelet-1').source_spikelet_id, 'source-spikelet-1');
  assert.equal(inspectionRecordForSpikelet(result,'missing'), null);
});

test('product contract projects back to the editable canvas view without losing geometry', () => {
  const result = normalizeProductResult({
    schema: PRODUCT_RESULT_SCHEMA,
    source: {sha256:'source'},
    measurements: [{
      id: 'measurement-1',
      label: 'A1',
      origin: 'automatic',
      review: {status:'modified', modified:true, confirmed:false},
      spikelet: {id:'spikelet-1', polygon:[[1,1],[4,1],[4,5],[1,5]]},
      representative_awn: {id:'awn-1', measurement_path:[[2,1],[2,8]], length_mm:7.2},
      provenance: {source:'test'}
    }],
    display_layers: {
      detection_evidence: [{id:'e1'}],
      awn_candidates: [{id:'a1'}],
      representative_awns: [{id:'r1'}]
    },
    inspection: {schema:'unified_growth_inspection_v1',stages:['source'],records:{'spikelet-1':{steps:[]}},support_pool:[]},
    run: {model:{name:'m'},pipeline:{name:'p'},duration_seconds:2.0,timings:{}}
  });

  const groups = editableGroupsFromProductResult(result);
  assert.deepEqual(groups, [{
    uid:'spikelet-1',
    name:'A1',
    polygon:[[1,1],[4,1],[4,5],[1,5]],
    line:[[2,1],[2,8]],
    origin:'automatic',
    modified:true,
    confirmed:false,
    autoReviewStatus:'automatic',
    reviewReasons:[],
    reviewSignals:{},
    modelAwnId:'awn-1'
  }]);

  assert.deepEqual(displayLayersFromProductResult(result), {
    raw:[{id:'e1'}],
    candidates:[{id:'a1'}],
    representatives:[{id:'r1'}]
  });
  assert.deepEqual(resultSummary(result), {
    spikelet_count:1,
    measurement_path_count:1,
    duration_seconds:2
  });
});

test('missing representative path remains an explicit missing measurement', () => {
  const result = normalizeProductResult({
    groups: [{
      uid:'spikelet-2',
      name:'2',
      polygon:[[0,0],[2,0],[2,2]],
      line:[],
      origin:'manual',
      modified:true
    }]
  });
  assert.equal(result.measurements[0].review.status, 'missing_measurement');
  assert.equal(resultSummary(result).measurement_path_count, 0);
});
