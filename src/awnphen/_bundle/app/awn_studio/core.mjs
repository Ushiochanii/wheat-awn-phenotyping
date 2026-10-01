export const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
// Group neighboring spikelet centers into rows, then read each row left to right.
// When automatic reconstruction supplies an orientation, order in that same
// canonical frame so numbering is invariant to page rotation.
export function readingOrder(groups,rotationDeg=0){
 const angle=Number.isFinite(Number(rotationDeg))?Number(rotationDeg)*Math.PI/180:0,c=Math.cos(angle),s=Math.sin(angle),rotate=([x,y])=>[c*x-s*y,s*x+c*y];
 const boxes=groups.map(g=>{const points=g.polygon.map(rotate),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);return{g,x:(Math.min(...xs)+Math.max(...xs))/2,y:(Math.min(...ys)+Math.max(...ys))/2,h:Math.max(...ys)-Math.min(...ys)};});
 const heights=boxes.map(b=>b.h).sort((a,b)=>a-b),gap=(heights[Math.floor(heights.length/2)]||1)*1.5,rows=[];
 for(const b of boxes.sort((a,b)=>a.y-b.y)){let row=rows.at(-1);if(!row||b.y-row.y>gap){row={y:b.y,items:[]};rows.push(row);}row.items.push(b);row.y=row.items.reduce((s,v)=>s+v.y,0)/row.items.length;}
 return rows.flatMap(row=>row.items.sort((a,b)=>a.x-b.x).map(b=>b.g));
}
export const pathLength=points=>points.slice(1).reduce((s,p,i)=>s+distance(points[i],p),0);
export function simplifyPathDP1(points,tolerance=1){
 if(points.length<3||tolerance<=0)return points.map(p=>[...p]);
 const keep=new Set([0,points.length-1]),stack=[[0,points.length-1]],limit=tolerance*tolerance;
 while(stack.length){const [start,end]=stack.pop(),a=points[start],b=points[end],dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;let farthest=0,index=-1;
  for(let i=start+1;i<end;i++){const p=points[i],t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0,x=a[0]+t*dx,y=a[1]+t*dy,d=(p[0]-x)**2+(p[1]-y)**2;if(d>farthest){farthest=d;index=i;}}
  if(index>=0&&farthest>limit){keep.add(index);stack.push([start,index],[index,end]);}
 }
 return [...keep].sort((a,b)=>a-b).map(i=>[...points[i]]);
}
export function lengthMM(group,calibration){return group.line?.length>=2&&calibration?pathLength(group.line)*calibration.mm/pathLength(calibration.points):null;}
export function validName(name,groups,uid){name=name.trim();return name.length>0&&name.length<=80&&!groups.some(g=>g.uid!==uid&&g.name===name);}
export function nextName(groups){let n=1;while(groups.some(g=>g.name===String(n)))n++;return String(n);}
export function nearestSegment(points,p,closed=false){let best={index:0,distance:Infinity,point:p};for(let i=0;i<points.length-(closed?0:1);i++){const a=points[i],b=points[(i+1)%points.length],dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)):0,q=[a[0]+t*dx,a[1]+t*dy],d=distance(q,p);if(d<best.distance)best={index:i,distance:d,point:q};}return best;}
export function csv(page){const quote=v=>'"'+String(v).replaceAll('"','""')+'"';return '\ufeffID,Awn length (mm)\r\n'+page.groups.map(g=>{let name=g.name;if(/^[\s]*[=+@-]/.test(name))name="'"+name;const len=lengthMM(g,page.calibration);return quote(name)+','+(len===null?'':len.toFixed(3));}).join('\r\n');}
export function validateProject(project){
 if(project?.schema!=='awn-studio-v1'||!Array.isArray(project.pages)||!project.pages.length)throw Error('Not a valid Awn Studio project file.');
 const ids=new Set();
 for(const p of project.pages){if(!p.id||ids.has(p.id))throw Error('Duplicate image identifier.');ids.add(p.id);const hasImage=/^data:image\/(png|jpeg|webp);base64,/.test(p.src??'')||(typeof p.assetRef==='string'&&p.assetRef.length>0);if(!Number.isFinite(p.width)||!Number.isFinite(p.height)||p.width<=0||p.height<=0||typeof p.name!=='string'||!hasImage||!Array.isArray(p.groups))throw Error('Invalid image metadata.');
 const check=points=>Array.isArray(points)&&points.every(q=>Array.isArray(q)&&q.length===2&&q.every(Number.isFinite)&&q[0]>=0&&q[1]>=0&&q[0]<=p.width&&q[1]<=p.height);
 if(p.calibration&&(!check(p.calibration.points)||p.calibration.points.length!==2||pathLength(p.calibration.points)<=0||!Number.isFinite(p.calibration.mm)||p.calibration.mm<=0))throw Error('Invalid calibration.');
 const names=new Set(),uids=new Set();for(const g of p.groups){if(typeof g.uid!=='string'||uids.has(g.uid)||typeof g.name!=='string'||!g.name.trim()||g.name.length>80||names.has(g.name)||!check(g.polygon)||g.polygon.length<3||!check(g.line)||g.line.length===1)throw Error('Invalid object ID or geometry.');names.add(g.name);uids.add(g.uid);}}
 return project;
}
// Uncompressed ZIP, UTF-8 names. No CDN or runtime dependencies.
export function zipFiles(files){const enc=new TextEncoder(),chunks=[],central=[];let offset=0;const crc=data=>{let c=0xffffffff;for(const b of data){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;};
 for(const f of files){const name=enc.encode(f.name),data=enc.encode(f.content),c=crc(data),local=new Uint8Array(30+name.length),v=new DataView(local.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint32(14,c,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);local.set(name,30);chunks.push(local,data);const cd=new Uint8Array(46+name.length),d=new DataView(cd.buffer);d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x800,true);d.setUint32(16,c,true);d.setUint32(20,data.length,true);d.setUint32(24,data.length,true);d.setUint16(28,name.length,true);d.setUint32(42,offset,true);cd.set(name,46);central.push(cd);offset+=local.length+data.length;}
 const end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,files.length,true);v.setUint16(10,files.length,true);v.setUint32(12,central.reduce((s,x)=>s+x.length,0),true);v.setUint32(16,offset,true);return new Blob([...chunks,...central,end],{type:'application/zip'});
}
