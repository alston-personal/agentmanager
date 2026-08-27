/* LayoutLib Spatial Semantics v0.1.0
 * Deterministic, token-free semantic enrichment for floor-plan IR.
 * Detects collinear wall openings, classifies door/window evidence,
 * infers basic door swing metadata, segments rooms, and connects openings to rooms.
 */
(function(global){
'use strict';
const Core=global.LayoutLibBrowser;
if(!Core)throw new Error('LayoutLibBrowser is required before LayoutLibSpatialSemantics');
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const dist=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const clone=v=>JSON.parse(JSON.stringify(v));

function gray(data,i){return Math.round(.299*data[i]+.587*data[i+1]+.114*data[i+2])}
function isDark(imageData,x,y,threshold){
  x=Math.round(x);y=Math.round(y);
  if(x<0||y<0||x>=imageData.width||y>=imageData.height)return false;
  return gray(imageData.data,(y*imageData.width+x)*4)<=threshold;
}
function wallPx(ir,w){
  const a=Core.worldToSourcePx(ir.coordinate_frame,w.start),b=Core.worldToSourcePx(ir.coordinate_frame,w.end);
  const horizontal=Math.abs(b.x-a.x)>=Math.abs(b.y-a.y);
  if(horizontal&&a.x>b.x)return{a:b,b:a,axis:'h',coord:(a.y+b.y)/2,wall:w};
  if(!horizontal&&a.y>b.y)return{a:b,b:a,axis:'v',coord:(a.x+b.x)/2,wall:w};
  return{a,b,axis:horizontal?'h':'v',coord:horizontal?(a.y+b.y)/2:(a.x+b.x)/2,wall:w};
}
function candidateOpenings(ir,opts={}){
  const minGap=Number(opts.min_opening_px||10),maxGap=Number(opts.max_opening_px||110),lineTol=Number(opts.opening_line_tolerance_px||6);
  const ws=(ir.walls||[]).map(w=>wallPx(ir,w)),out=[];
  for(let i=0;i<ws.length;i++)for(let j=i+1;j<ws.length;j++){
    const u=ws[i],v=ws[j]; if(u.axis!==v.axis||Math.abs(u.coord-v.coord)>lineTol)continue;
    let start,end,gap;
    if(u.axis==='h'){
      if(u.b.x<=v.a.x){start=u.b;end=v.a}else if(v.b.x<=u.a.x){start=v.b;end=u.a}else continue;
      gap=end.x-start.x;
    }else{
      if(u.b.y<=v.a.y){start=u.b;end=v.a}else if(v.b.y<=u.a.y){start=v.b;end=u.a}else continue;
      gap=end.y-start.y;
    }
    if(gap<minGap||gap>maxGap)continue;
    out.push({id:`opening-${String(out.length+1).padStart(4,'0')}`,axis:u.axis,start_px:{...start},end_px:{...end},width_px:gap,wall_ids:[u.wall.id,v.wall.id],line_coord:(u.coord+v.coord)/2});
  }
  return out;
}
function classifyOpening(imageData,o,threshold,opts={}){
  const radius=Math.round(clamp(Number(opts.opening_evidence_radius_px||18),8,40));
  const mid={x:(o.start_px.x+o.end_px.x)/2,y:(o.start_px.y+o.end_px.y)/2};
  const x0=Math.floor(Math.min(o.start_px.x,o.end_px.x)-3),x1=Math.ceil(Math.max(o.start_px.x,o.end_px.x)+3);
  const y0=Math.floor(Math.min(o.start_px.y,o.end_px.y)-3),y1=Math.ceil(Math.max(o.start_px.y,o.end_px.y)+3);
  let axisInk=0,sideInk=0,total=0,sideA=0,sideB=0;
  const rx0=o.axis==='h'?x0:Math.floor(mid.x-radius),rx1=o.axis==='h'?x1:Math.ceil(mid.x+radius);
  const ry0=o.axis==='h'?Math.floor(mid.y-radius):y0,ry1=o.axis==='h'?Math.ceil(mid.y+radius):y1;
  for(let y=ry0;y<=ry1;y++)for(let x=rx0;x<=rx1;x++){
    if(!isDark(imageData,x,y,threshold))continue; total++;
    const d=o.axis==='h'?Math.abs(y-o.line_coord):Math.abs(x-o.line_coord);
    if(d<=2)axisInk++; else if(d<=radius){sideInk++; if((o.axis==='h'?y-mid.y:x-mid.x)<0)sideA++; else sideB++;}
  }
  const denom=Math.max(1,axisInk+sideInk),density=total/Math.max(1,(rx1-rx0+1)*(ry1-ry0+1));
  const sideRatio=sideInk/denom,axisRatio=axisInk/denom;
  let doorScore=clamp(sideRatio*1.15 + (density>.015&&density<.38?.18:0),0,1);
  let windowScore=clamp(axisRatio*1.05 + (density>.012&&density<.45?.12:0),0,1);
  if(total<5){doorScore*=.25;windowScore*=.25}
  let semantic='opening',confidence=Math.max(doorScore,windowScore);
  if(doorScore>=.58&&doorScore>=windowScore+.08)semantic='door';
  else if(windowScore>=.58&&windowScore>=doorScore+.08)semantic='window';
  const hingeCounts=[0,0];
  for(let k=0;k<2;k++){
    const p=k?o.end_px:o.start_px;
    for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){
      if(dx*dx+dy*dy>radius*radius||!isDark(imageData,p.x+dx,p.y+dy,threshold))continue;
      const off=o.axis==='h'?Math.abs(dy):Math.abs(dx);if(off>3)hingeCounts[k]++;
    }
  }
  const hinge=hingeCounts[0]>=hingeCounts[1]?'start':'end';
  const swingSide=sideA>=sideB?'negative_normal':'positive_normal';
  return{...o,semantic,confidence:+confidence.toFixed(3),evidence:{axis_ink:axisInk,side_ink:sideInk,density:+density.toFixed(4),door_score:+doorScore.toFixed(3),window_score:+windowScore.toFixed(3)},hinge,swing_side:swingSide};
}
function lineCells(a,b,step){
  const x0=a.x/step,y0=a.y/step,x1=b.x/step,y1=b.y/step,n=Math.max(1,Math.ceil(Math.hypot(x1-x0,y1-y0)*2)),out=[];
  for(let i=0;i<=n;i++){const t=i/n;out.push([Math.round(x0+(x1-x0)*t),Math.round(y0+(y1-y0)*t)])}return out;
}
function segmentRooms(ir,openings,opts={}){
  const step=Math.max(3,Math.round(Number(opts.room_grid_px||6))),gw=Math.ceil(ir.image_width_px/step),gh=Math.ceil(ir.image_height_px/step);
  if(gw*gh>900000)return[];
  const blocked=Array.from({length:gh},()=>new Uint8Array(gw));
  const markLine=(a,b,r=1)=>{for(const[x,y]of lineCells(a,b,step))for(let yy=y-r;yy<=y+r;yy++)for(let xx=x-r;xx<=x+r;xx++)if(xx>=0&&yy>=0&&xx<gw&&yy<gh)blocked[yy][xx]=1};
  for(const w of ir.walls||[]){const p=wallPx(ir,w);markLine(p.a,p.b,1)}
  for(const o of openings||[])markLine(o.start_px,o.end_px,1); // close openings while segmenting room topology
  const exterior=Array.from({length:gh},()=>new Uint8Array(gw)),q=[];
  const seed=(x,y)=>{if(x>=0&&y>=0&&x<gw&&y<gh&&!blocked[y][x]&&!exterior[y][x]){exterior[y][x]=1;q.push([x,y])}};
  for(let x=0;x<gw;x++){seed(x,0);seed(x,gh-1)}for(let y=0;y<gh;y++){seed(0,y);seed(gw-1,y)}
  for(let h=0;h<q.length;h++){const[x,y]=q[h];seed(x+1,y);seed(x-1,y);seed(x,y+1);seed(x,y-1)}
  const labels=Array.from({length:gh},()=>new Int32Array(gw)),rooms=[];let label=0;
  for(let y=1;y<gh-1;y++)for(let x=1;x<gw-1;x++)if(!blocked[y][x]&&!exterior[y][x]&&!labels[y][x]){
    label++;const qq=[[x,y]];labels[y][x]=label;let n=0,sx=0,sy=0,minx=x,maxx=x,miny=y,maxy=y;
    for(let h=0;h<qq.length;h++){const[cx,cy]=qq[h];n++;sx+=cx;sy+=cy;minx=Math.min(minx,cx);maxx=Math.max(maxx,cx);miny=Math.min(miny,cy);maxy=Math.max(maxy,cy);
      for(const[nx,ny]of[[cx+1,cy],[cx-1,cy],[cx,cy+1],[cx,cy-1]])if(nx>0&&ny>0&&nx<gw-1&&ny<gh-1&&!blocked[ny][nx]&&!exterior[ny][nx]&&!labels[ny][nx]){labels[ny][nx]=label;qq.push([nx,ny])}}
    if(n<Number(opts.min_room_cells||24))continue;
    const mpp=Number(ir.meters_per_pixel||ir.coordinate_frame?.meters_per_pixel||.02);
    rooms.push({id:`room-${String(rooms.length+1).padStart(3,'0')}`,label,centroid_px:{x:(sx/n)*step,y:(sy/n)*step},bbox_px:{x:minx*step,y:miny*step,width:(maxx-minx+1)*step,height:(maxy-miny+1)*step},area_m2:+(n*step*step*mpp*mpp).toFixed(2),source:'auto_topology'});
  }
  const roomByLabel=new Map(rooms.map(r=>[r.label,r.id]));
  const roomAt=p=>{const x=clamp(Math.round(p.x/step),0,gw-1),y=clamp(Math.round(p.y/step),0,gh-1);return roomByLabel.get(labels[y][x])||null};
  for(const o of openings){const m={x:(o.start_px.x+o.end_px.x)/2,y:(o.start_px.y+o.end_px.y)/2},d=Math.max(10,step*2),p1=o.axis==='h'?{x:m.x,y:m.y-d}:{x:m.x-d,y:m.y},p2=o.axis==='h'?{x:m.x,y:m.y+d}:{x:m.x+d,y:m.y};o.connects=[roomAt(p1),roomAt(p2)].filter(Boolean)}
  return rooms.map(({label,...r})=>r);
}
function enrich(ir,imageData,opts={}){
  const threshold=Number(ir.detection?.threshold??opts.threshold??128);
  const raw=candidateOpenings(ir,opts).map(o=>classifyOpening(imageData,o,threshold,opts));
  const rooms=segmentRooms(ir,raw,opts),mpp=Number(ir.meters_per_pixel||ir.coordinate_frame?.meters_per_pixel||.02);
  const openings=raw.map(o=>({...o,width_m:+(o.width_px*mpp).toFixed(3)}));
  const doors=openings.filter(o=>o.semantic==='door').map(o=>({id:`door-${o.id.split('-').pop()}`,opening_id:o.id,wall_ids:o.wall_ids,width_m:o.width_m,hinge:o.hinge,swing_side:o.swing_side,type:'single_swing',confidence:o.confidence,connects:o.connects||[]}));
  const windows=openings.filter(o=>o.semantic==='window').map(o=>({id:`window-${o.id.split('-').pop()}`,opening_id:o.id,wall_ids:o.wall_ids,width_m:o.width_m,type:'window',confidence:o.confidence,connects:o.connects||[]}));
  const out=clone(ir);out.openings=openings;out.doors=doors;out.windows=windows;out.rooms=rooms;out.semantic_summary={walls:(out.walls||[]).length,openings:openings.length,doors:doors.length,windows:windows.length,rooms:rooms.length,engine:'layoutlib-spatial-semantics/v0.1',token_cost:0};return out;
}
function install(){
  if(Core.__spatialSemanticsInstalled)return Core;
  const base=Core.analyzeImageData;
  Core.analyzeImageData=function(imageData,opts={}){return enrich(base.call(Core,imageData,opts),imageData,opts)};
  Core.enrichSpatialSemantics=enrich;Core.detectOpeningCandidates=candidateOpenings;Core.segmentRooms=segmentRooms;Core.__spatialSemanticsInstalled=true;return Core;
}
const api={version:'0.1.0',candidateOpenings,classifyOpening,segmentRooms,enrich,install};
global.LayoutLibSpatialSemantics=api;install();
})(window);
