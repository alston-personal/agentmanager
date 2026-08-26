/* LayoutLib v0.6.1 staged extension — NOT wired to production deployment.
 * Adds pre-analysis editable documents, rectangle selection, and selection deletion.
 */
(function(global){
'use strict';
const lib=global.LayoutLibBrowser;
if(!lib||lib.version!=='0.6.0') throw new Error('LayoutLib v0.6.0 must be loaded before v0.6.1 staged extension');
const clone=v=>JSON.parse(JSON.stringify(v));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

function createEditableDocument(widthPx,heightPx,opts={}){
  const W=Math.max(1,Math.round(Number(widthPx)||1)),H=Math.max(1,Math.round(Number(heightPx)||1));
  const mpp=Math.max(.000001,Number(opts.meters_per_pixel||opts.scale_calibration?.meters_per_pixel||.02));
  const region=opts.analysis_region_px||{x:0,y:0,width:W,height:H};
  return {
    version:'0.6.1',units:'m',image_width_px:W,image_height_px:H,meters_per_pixel:mpp,
    coordinate_frame:{anchor_px:{x:region.x||0,y:region.y||0},anchor_world_m:{x:0,y:0},meters_per_pixel:mpp,rotation_deg:0,image_y_axis:'down'},
    analysis_region_px:clone(region),scale_calibration:opts.scale_calibration||null,
    detection:{threshold:clamp(Number(opts.threshold??128),0,255),min_wall_length_px:Math.max(2,Number(opts.min_wall_length_px||16)),max_wall_thickness_px:Math.max(1,Number(opts.max_wall_thickness_px||16)),state:'uncommitted'},
    geometry:{wall_height_m:Math.max(.1,Number(opts.wall_height_m||2.7)),wall_thickness_m:Math.max(.01,Number(opts.wall_thickness_m||.12)),floor_enabled:opts.floor_enabled!==false,floor_thickness_m:Math.max(.01,Number(opts.floor_thickness_m||.15))},
    walls:[],edits:[],profile_prediction:opts.profile_prediction||null,document_state:'editable_before_analysis'
  };
}

function wallPx(ir,wall){return{a:lib.worldToSourcePx(ir.coordinate_frame,wall.start),b:lib.worldToSourcePx(ir.coordinate_frame,wall.end)}}
function pointInRect(p,r){return p.x>=r.x&&p.x<=r.x+r.width&&p.y>=r.y&&p.y<=r.y+r.height}
function segmentIntersectsRect(a,b,r){
  if(pointInRect(a,r)||pointInRect(b,r))return true;
  const edges=[[{x:r.x,y:r.y},{x:r.x+r.width,y:r.y}],[{x:r.x+r.width,y:r.y},{x:r.x+r.width,y:r.y+r.height}],[{x:r.x+r.width,y:r.y+r.height},{x:r.x,y:r.y+r.height}],[{x:r.x,y:r.y+r.height},{x:r.x,y:r.y}]];
  const cross=(p,q,s,t)=>{const ax=q.x-p.x,ay=q.y-p.y,bx=t.x-s.x,by=t.y-s.y,d=ax*by-ay*bx;if(Math.abs(d)<1e-9)return false;const cx=s.x-p.x,cy=s.y-p.y,u=(cx*by-cy*bx)/d,v=(cx*ay-cy*ax)/d;return u>=0&&u<=1&&v>=0&&v<=1};
  return edges.some(([s,t])=>cross(a,b,s,t));
}
function normalizeRect(a,b){return{x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(b.x-a.x),height:Math.abs(b.y-a.y)}}
function selectWallsInRectPx(ir,aPx,bPx,opts={}){
  const r=normalizeRect(aPx,bPx),contain=opts.mode!=='intersect';
  const wallIds=[];
  for(const w of ir.walls||[]){const{a,b}=wallPx(ir,w);if(contain?(pointInRect(a,r)&&pointInRect(b,r)):segmentIntersectsRect(a,b,r))wallIds.push(w.id)}
  return{rect:r,wall_ids:wallIds,mode:contain?'contain':'intersect'};
}
function selectWallNearPx(ir,pPx,radiusPx=8){
  let best=null,bestD=Infinity;
  for(const w of ir.walls||[]){const{a,b}=wallPx(ir,w),vx=b.x-a.x,vy=b.y-a.y,l2=vx*vx+vy*vy||1,t=clamp(((pPx.x-a.x)*vx+(pPx.y-a.y)*vy)/l2,0,1),q={x:a.x+t*vx,y:a.y+t*vy},d=Math.hypot(pPx.x-q.x,pPx.y-q.y);if(d<bestD){bestD=d;best=w.id}}
  return bestD<=radiusPx?best:null;
}
function deleteWallsById(ir,ids){
  const out=clone(ir),wanted=new Set(ids||[]),removed=[];
  out.walls=(out.walls||[]).filter(w=>{if(!wanted.has(w.id))return true;const px=wallPx(out,w);removed.push({wall_id:w.id,start_px:px.a,end_px:px.b,source:w.source});return false});
  if(removed.length)(out.edits||(out.edits=[])).push({op:'delete_walls',removed});
  return out;
}

Object.assign(lib,{version:'0.6.1-staged',createEditableDocument,selectWallsInRectPx,selectWallNearPx,deleteWallsById});
})(window);
