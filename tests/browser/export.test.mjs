import test from 'node:test';
import assert from 'node:assert/strict';
import {detailedProjectCsv} from '../../app/awn_studio/export.mjs';

test('detailed project export preserves automatic and final lengths with provenance', () => {
  const source = {
    id:'source',
    name:'IMG_0001.jpg',
    calibration:{points:[[0,0],[10,0]],mm:10},
    groups:[]
  };
  const result = {
    id:'result',
    sourcePageId:'source',
    sourceName:'IMG_0001.jpg',
    name:'IMG_0001.jpg · automatic measurement',
    calibration:{points:[[0,0],[10,0]],mm:10},
    groups:[{
      uid:'spikelet-1',
      name:'1',
      polygon:[[0,0],[1,0],[1,1]],
      line:[[0,0],[0,6]],
      origin:'automatic',
      modified:true,
      confirmed:false,
      modelAwnId:'candidate-1'
    }],
    inference:{
      schema:'awn-studio-result-v2',
      source:{},
      measurements:[{
        id:'m1',
        label:'1',
        origin:'automatic',
        review:{status:'automatic',modified:false,confirmed:false},
        spikelet:{id:'spikelet-1',polygon:[[0,0],[1,0],[1,1]]},
        representative_awn:{
          id:'candidate-1',
          measurement_path:[[0,0],[0,5]],
          length_mm:5
        },
        provenance:{}
      }],
      display_layers:{detection_evidence:[],awn_candidates:[],representative_awns:[]},
      inspection:{stages:[],records:{}},
      run:{
        model:{name:'example-model'},
        pipeline:{name:'unified-growth'},
        timings:{},
        diagnostics:{}
      }
    }
  };

  const csv = detailedProjectCsv([source,result]);
  const lines = csv.replace(/^\ufeff/,'').split('\r\n');
  assert.equal(lines.length,2);
  assert.match(lines[0],/Automatic awn length \(mm\)/);
  assert.match(lines[0],/Final awn length \(mm\)/);
  assert.match(lines[1],/"IMG_0001\.jpg","1","5\.000","6\.000","Edited","","true","false","example-model","unified-growth"/);
});

test('detailed export leaves missing automatic and final measurements blank', () => {
  const manual = {
    id:'manual',
    name:'manual.jpg',
    calibration:{points:[[0,0],[1,0]],mm:1},
    groups:[{
      uid:'manual-1',
      name:'A1',
      polygon:[[0,0],[1,0],[1,1]],
      line:[],
      origin:'manual',
      modified:true,
      confirmed:false
    }]
  };
  const csv = detailedProjectCsv([manual]);
  assert.match(csv,/"manual\.jpg","A1","","","Missing","","true","false","",""/);
});
