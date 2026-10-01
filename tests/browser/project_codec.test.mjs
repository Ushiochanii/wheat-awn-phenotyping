import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PROJECT_STORAGE_SCHEMA,
  decodeProject,
  encodeProject
} from '../../app/awn_studio/project_codec.mjs';

const dataUrl = 'data:image/png;base64,' + 'A'.repeat(2048);

function runtimeProject() {
  return {
    schema:'awn-studio-v1',
    updatedAt:'2026-09-27T00:00:00.000Z',
    pages:[
      {
        id:'source',
        name:'IMG_0001.png',
        src:dataUrl,
        width:100,
        height:80,
        groups:[],
        calibration:{points:[[0,0],[10,0]],mm:5}
      },
      {
        id:'result',
        sourcePageId:'source',
        sourceName:'IMG_0001.png',
        name:'IMG_0001.png · automatic measurement',
        src:dataUrl,
        width:100,
        height:80,
        groups:[{
          uid:'spikelet-1',
          name:'1',
          polygon:[[0,0],[5,0],[5,5]],
          line:[[2,0],[2,20]],
          origin:'automatic',
          modified:false,
          confirmed:false,
          modelAwnId:'awn-1'
        }],
        calibration:{points:[[0,0],[10,0]],mm:6},
        inference:{schema:'awn-studio-result-v2'}
      }
    ]
  };
}

test('v2 storage omits duplicated source image bytes from result pages', () => {
  const encoded = encodeProject(runtimeProject());
  assert.equal(encoded.schema, PROJECT_STORAGE_SCHEMA);
  assert.equal(encoded.pages[0].src, dataUrl);
  assert.equal('src' in encoded.pages[1], false);
  assert.equal(JSON.stringify(encoded).split('data:image/png;base64,').length - 1, 1);
});

test('v2 storage round-trips result pages and preserves result calibration', () => {
  const original = runtimeProject();
  const decoded = decodeProject(encodeProject(original));
  assert.equal(decoded.schema, 'awn-studio-v1');
  assert.equal(decoded.pages[1].src, dataUrl);
  assert.deepEqual(decoded.pages[1].calibration, original.pages[1].calibration);
  assert.deepEqual(decoded.pages[1].groups, original.pages[1].groups);
  assert.equal(decoded.pages[1].sourcePageId, 'source');
});

test('legacy v1 project files remain readable', () => {
  const original = runtimeProject();
  const decoded = decodeProject(original);
  assert.deepEqual(decoded, original);
});

test('v2 result pages must match source image dimensions', () => {
  const encoded = encodeProject(runtimeProject());
  encoded.pages.find(page => page.id === 'result').width = 101;
  assert.throws(
    () => decodeProject(encoded),
    /does not match its source image dimensions/
  );
});

test('v2 result pages cannot reference a missing source image', () => {
  const encoded = encodeProject(runtimeProject());
  encoded.pages = encoded.pages.filter(page => page.id !== 'source');
  assert.throws(
    () => decodeProject(encoded),
    /references a missing source image/
  );
});
