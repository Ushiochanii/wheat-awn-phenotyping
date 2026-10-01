import test from 'node:test';
import assert from 'node:assert/strict';
import {
  cascadePageIds,
  currentMeasurementPage,
  exportableMeasurementPages,
  hasMeasurementResult,
  isMeasurementResultPage,
  latestMeasurementResult,
  matchingUncalibratedSources,
  navigationPages,
  navigationTarget,
  pendingSourcePages,
  projectPageStatus,
  measurementResultModelId,
  uncalibratedPendingSourcePages
} from '../../app/awn_studio/workflow.mjs';

const calibration = {points:[[0,0],[10,0]], mm:1};

test('workflow separates source images from measurement result pages', () => {
  const source = {id:'source-1', calibration};
  const result = {id:'result-1', sourcePageId:'source-1', inference:{schema:'awn-studio-result-v2'}};
  const pages = [source,result];

  assert.equal(isMeasurementResultPage(source), false);
  assert.equal(isMeasurementResultPage(result), true);
  assert.equal(isMeasurementResultPage({id:'lazy-result', inferenceRef:'lazy-result'}), true);
  assert.equal(isMeasurementResultPage({id:'typed-result', pageKind:'measurement_result'}), true);
  assert.equal(hasMeasurementResult(pages,'source-1'), true);
  assert.equal(projectPageStatus(source,pages), 'measured');
  assert.equal(projectPageStatus(result,pages), 'result');
});

test('only calibrated sources without a result enter the pending queue', () => {
  const ready = {id:'ready', calibration};
  const uncalibrated = {id:'uncalibrated', calibration:null};
  const measured = {id:'measured', calibration};
  const measuredResult = {id:'measured-result', sourcePageId:'measured', inference:{}};
  const historicalDemo = {id:'demo', calibration, demo:true};
  const pages = [ready,uncalibrated,measured,measuredResult,historicalDemo];

  assert.deepEqual(pendingSourcePages(pages).map(page=>page.id), ['ready']);
  assert.deepEqual(uncalibratedPendingSourcePages(pages).map(page=>page.id), ['uncalibrated']);
  assert.equal(projectPageStatus(ready,pages), 'ready');
  assert.equal(projectPageStatus(uncalibrated,pages), 'needs_calibration');
});

test('deleting a result makes its calibrated source pending again', () => {
  const source = {id:'source', calibration};
  const result = {id:'result', sourcePageId:'source', inference:{}};
  assert.equal(pendingSourcePages([source,result]).length, 0);
  assert.deepEqual(pendingSourcePages([source]).map(page=>page.id), ['source']);
});

test('pending is model-specific for the same source image', () => {
  const source = {id:'source', calibration};
  const controlled = {
    id:'controlled',
    sourcePageId:'source',
    pageKind:'measurement_result',
    modelId:'controlled-v2-stage1'
  };
  const yoloM = {
    id:'yolo-m',
    sourcePageId:'source',
    pageKind:'measurement_result',
    inferenceMeta:{modelId:'yolo11m-benchmark'}
  };

  assert.equal(hasMeasurementResult([source,controlled],'source','controlled-v2-stage1'), true);
  assert.equal(hasMeasurementResult([source,controlled],'source','yolo11m-benchmark'), false);
  assert.deepEqual(
    pendingSourcePages([source,controlled],'yolo11m-benchmark').map(page=>page.id),
    ['source']
  );
  assert.equal(
    pendingSourcePages([source,controlled,yoloM],'yolo11m-benchmark').length,
    0
  );
});

test('legacy results map to the original Controlled v2 model', () => {
  const legacy = {id:'legacy', sourcePageId:'source', inference:{schema:'awn-studio-result-v2'}};
  assert.equal(measurementResultModelId(legacy), 'controlled-v2-stage1');
});

test('navigation keeps one card per source and opens the latest result', () => {
  const source = {id:'source', calibration};
  const first = {id:'result-1', sourcePageId:'source', inference:{}, groups:[{uid:'a'}]};
  const latest = {id:'result-2', sourcePageId:'source', inference:{}, groups:[{uid:'b'}]};
  const standalone = {id:'standalone', inference:{}, groups:[]};
  const pages = [source,first,latest,standalone];

  assert.deepEqual(navigationPages(pages).map(page=>page.id), ['source','standalone']);
  assert.equal(latestMeasurementResult(pages,'source').id, 'result-2');
  assert.equal(navigationTarget(source,pages).id, 'result-2');
  assert.equal(navigationTarget(standalone,pages).id, 'standalone');
});

test('current measurement follows a source page to its latest result', () => {
  const source = {id:'source', calibration, groups:[]};
  const first = {id:'first', sourcePageId:'source', inference:{}, groups:[{uid:'a'}]};
  const latest = {id:'latest', sourcePageId:'source', inference:{}, groups:[{uid:'b'}]};
  const manual = {id:'manual', calibration, groups:[{uid:'manual'}]};
  const empty = {id:'empty', calibration, groups:[]};
  const pages = [source,first,latest,manual,empty];
  assert.equal(currentMeasurementPage(source,pages).id, 'latest');
  assert.equal(currentMeasurementPage(first,pages).id, 'first');
  assert.equal(currentMeasurementPage(manual,pages).id, 'manual');
  assert.equal(currentMeasurementPage(empty,pages), null);
});

test('export selects the latest result or a manual-only measurement page', () => {
  const source = {id:'source', calibration, groups:[]};
  const oldResult = {id:'old', sourcePageId:'source', inference:{}, groups:[{uid:'old'}]};
  const newResult = {id:'new', sourcePageId:'source', inference:{}, groups:[{uid:'new'}]};
  const manual = {id:'manual', calibration, groups:[{uid:'manual'}]};
  const empty = {id:'empty', calibration, groups:[]};
  assert.deepEqual(
    exportableMeasurementPages([source,oldResult,newResult,manual,empty]).map(page=>page.id),
    ['new','manual']
  );
});

test('matching calibration targets require same dimensions and no existing calibration', () => {
  const reference = {id:'reference', width:3508, height:2480, calibration};
  const matching = {id:'matching', width:3508, height:2480, calibration:null};
  const wrongSize = {id:'wrong-size', width:1920, height:1080, calibration:null};
  const alreadyCalibrated = {id:'calibrated', width:3508, height:2480, calibration};
  const demo = {id:'demo', width:3508, height:2480, calibration:null, demo:true};
  assert.deepEqual(
    matchingUncalibratedSources([reference,matching,wrongSize,alreadyCalibrated,demo],reference).map(page=>page.id),
    ['matching']
  );
});

test('deleting a source cascades to its measurement result pages', () => {
  const pages = [
    {id:'source'},
    {id:'result-1', sourcePageId:'source', inference:{}},
    {id:'result-2', sourcePageId:'source', inference:{}},
    {id:'other'}
  ];
  assert.deepEqual(
    [...cascadePageIds(pages,new Set(['source']))].sort(),
    ['result-1','result-2','source']
  );
});
