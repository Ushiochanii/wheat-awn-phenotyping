import test from 'node:test';
import assert from 'node:assert/strict';
import {pathLength,lengthMM,validName,nearestSegment,csv,validateProject,zipFiles} from '../../app/awn_studio/core.mjs';
test('arc length, scale change and missing measurement',()=>{const g={line:[[0,0],[3,4],[6,4]]};assert.equal(pathLength(g.line),8);assert.equal(lengthMM(g,{points:[[0,0],[10,0]],mm:5}),4);assert.equal(lengthMM(g,{points:[[0,0],[10,0]],mm:10}),8);assert.equal(lengthMM({line:[]},{points:[[0,0],[10,0]],mm:5}),null);assert.equal(lengthMM(g,null),null);});
test('renaming remains unique within the image',()=>{const gs=[{uid:'a',name:'1'},{uid:'b',name:'2'}];assert.equal(validName(' 2 ',gs,'a'),false);assert.equal(validName('1',gs,'a'),true);assert.equal(validName('',gs,'a'),false);});
test('inserted vertex projected onto path does not change length',()=>{const pts=[[0,0],[10,0],[10,10]],n=nearestSegment(pts,[6,3]);assert.deepEqual(n.point,[6,0]);pts.splice(n.index+1,0,n.point);assert.equal(pathLength(pts),20);});
test('CSV includes exactly two columns, quotes IDs, missing stays blank',()=>{const p={calibration:{points:[[0,0],[10,0]],mm:10},groups:[{name:'a,"b',line:[[0,0],[3,4]]},{name:'=1+1',line:[]}]};assert.equal(csv(p),'\ufeffID,Awn length (mm)\r\n"a,""b",5.000\r\n"\'=1+1",');});
test('project rejects duplicate IDs, bad coordinates and zero scale',()=>{const p={schema:'awn-studio-v1',pages:[{id:'p',name:'p',width:100,height:100,src:'data:image/png;base64,AA==',calibration:null,groups:[{uid:'g',name:'1',polygon:[[0,0],[1,0],[1,1]],line:[]}]}]};assert.equal(validateProject(p),p);const b=structuredClone(p);b.pages[0].groups.push(structuredClone(b.pages[0].groups[0]));assert.throws(()=>validateProject(b));const c=structuredClone(p);c.pages[0].calibration={points:[[0,0],[0,0]],mm:5};assert.throws(()=>validateProject(c));const d=structuredClone(p);d.pages[0].groups[0].line=[[0,0],[101,1]];assert.throws(()=>validateProject(d));});
test('ZIP has matching file counts and UTF8 names',async()=>{const b=await zipFiles([{name:'图片.csv',content:'test'}]).arrayBuffer(),v=new DataView(b);assert.equal(v.getUint32(0,true),0x04034b50);assert.equal(v.getUint16(6,true),0x800);assert.equal(v.getUint32(b.byteLength-22,true),0x06054b50);assert.equal(v.getUint16(b.byteLength-12,true),1);});
import {readingOrder} from '../../app/awn_studio/core.mjs';
import {geometryPath} from '../../app/awn_studio/layers.mjs';
test('mask SVG preserves polygon holes and multipart geometry',()=>{
 const g={type:'MultiPolygon',coordinates:[[[[0,0],[10,0],[0,10],[0,0]],[[1,1],[2,1],[1,2],[1,1]]],[[[20,20],[30,20],[20,30],[20,20]]]]};
 const path=geometryPath(g);assert.equal((path.match(/M/g)||[]).length,3);assert.equal((path.match(/ Z/g)||[]).length,3);assert.ok(path.includes('M20,20'));
});
test('reading order keeps vertically staggered neighbors in one row',()=>{
 const make=(name,x,y)=>({name,polygon:[[x,y],[x+10,y],[x+10,y+20],[x,y+20]]});
 const groups=[make('right',90,92),make('left',10,101),make('middle',50,105),make('next',5,230)];
 assert.deepEqual(readingOrder(groups).map(g=>g.name),['left','middle','right','next']);
});
test('reading order uses the corrected canonical orientation when provided',()=>{
 const rect=(name,x,y)=>({name,polygon:[[x,y],[x+10,y],[x+10,y+20],[x,y+20]]});
 const canonical=[rect('left',10,20),rect('right',60,20),rect('next',10,100)];
 // Raw page is canonical geometry rotated -90 degrees. A +90 degree
 // reconstruction transform must recover the same numbering.
 const raw=canonical.map(g=>({...g,polygon:g.polygon.map(([x,y])=>[y,-x])}));
 assert.deepEqual(readingOrder(raw,90).map(g=>g.name),['left','right','next']);
});
