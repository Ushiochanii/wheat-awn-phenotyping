export function geometryPath(geometry){
 const polygons=geometry.type==='Polygon'?[geometry.coordinates]:geometry.type==='MultiPolygon'?geometry.coordinates:[];
 return polygons.flatMap(p=>p.map(ring=>ring.map(([x,y],i)=>`${i?'L':'M'}${x},${y}`).join(' ')+' Z')).join(' ');
}
export const timingLabels={model_load:'Model loading',prepare:'Image and tile preparation',tile_prediction:'Tile prediction and contour recovery',tile_merge:'Cross-tile merge',deduplicate:'Duplicate-instance handling',fragment_stitch:'Awn-fragment stitching',prediction_report:'Prediction report generation',physical_measurement:'Physical reconstruction, representative selection, and path measurement'};
