/* LayoutLib Editor Semantics v0.7.0
 * Pure library extension for editable Spatial IR corrections.
 * No DOM, no Layout Lab UI, no deployment behavior.
 */
(function(global){
'use strict';
const Core=global.LayoutLibBrowser;
if(!Core)throw new Error('LayoutLibBrowser is required before LayoutLibEditor');
const clone=v=>JSON.parse(JSON.stringify(v));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const MANUAL_OPS=new Set(['add_wall','erase_segments','delete_walls','move_wall']);

function createEditableDocument(W,H,o={}){
  W=Math.max(1,Math.round(W));H=Math.max(1,Math.round(H));
  const m=Math.max(.000001,Number(o.meters_per_pixel||.02));
  const r=o.analysis_region_px||{x:0,y:0,width:W,height:H};
  return{version:'0.7',units:'m',image_width_px:W,image_height_px:H,meters_per_pixel:m,
    coordinate_frame:{anchor_px:{x:r.x||0,y:r.y||0},anchor_world_m:{x:0,y:0},meters_per_pixel:m,rotation_deg:0,image_y_axis:'down'},
    analysis_region_px:clone(r),scale_calibration:o.scale_calibration||null,
    detection:{threshold:clamp(Number(o.threshold??128),0,255),min_wall_length_px:Number(o.min_wall_length_px||16),max_wall_thickness_px:Number(o.max_wall_thickness_px||16),state:'uncommitted'},
    geometry:{wall_height_m:Number(o.wall_height_m||2.7),wall_thickness_m:Number(o.wall_thickness_m||.12),floor_enabled:o.floor_enabled!==false,floor_thickness_m:.15},
    walls:[],edits:[],profile_prediction:o.profile_prediction||null,document_state:'editable_before_analysis'};
}

function wallEvidence(ir,w){
  return{wall_id:w.id,start_px:Core.worldToSourcePx(ir.coordinate_frame,w.start),end_px:Core.worldToSourcePx(ir.coordinate_frame,w.end),source:w.source||null};
}
function dist(a,b){return Math.hypot(a.x-b.x,a.y-b.y)}
function evidenceDistance(ir,w,e){
  if(!e?.start_px||!e?.end_px)return Infinity;
  const a=Core.worldToSourcePx(ir.coordinate_frame,w.start),b=Core.worldToSourcePx(ir.coordinate_frame,w.end);
  return Math.min(dist(a,e.start_px)+dist(b,e.end_px),dist(a,e.end_px)+dist(b,e.start_px));
}
function matchWallByEvidence(ir,e,opts={}){
  const walls=ir?.walls||[];
  let idx=walls.findIndex(w=>w.id===e?.wall_id);
  if(idx>=0)return{index:idx,wall:walls[idx],distance:0,match:'id'};
  const tolerance=Number(opts.tolerance_px||16);
  let best=-1,bestD=Infinity;
  walls.forEach((w,i)=>{
    if(e?.source&&w.source&&e.source!==w.source)return;
    const d=evidenceDistance(ir,w,e);
    if(d<bestD){bestD=d;best=i}
  });
  return best>=0&&bestD<=tolerance?{index:best,wall:walls[best],distance:bestD,match:'geometry'}:null;
}
function pointSeg(p,a,b){
  const vx=b.x-a.x,vy=b.y-a.y,l2=vx*vx+vy*vy||1;
  const t=clamp(((p.x-a.x)*vx+(p.y-a.y)*vy)/l2,0,1),x=a.x+t*vx,y=a.y+t*vy;
  return Math.hypot(p.x-x,p.y-y);
}
function selectWallNearPx(ir,p,radiusPx=8){
  let id=null,best=Infinity;
  for(const w of ir?.walls||[]){
    const a=Core.worldToSourcePx(ir.coordinate_frame,w.start),b=Core.worldToSourcePx(ir.coordinate_frame,w.end),d=pointSeg(p,a,b);
    if(d<best){best=d;id=w.id}
  }
  return best<=radiusPx?id:null;
}
function selectWallsInRectPx(ir,a,b){
  const r={x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(b.x-a.x),height:Math.abs(b.y-a.y)};
  const inside=p=>p.x>=r.x&&p.x<=r.x+r.width&&p.y>=r.y&&p.y<=r.y+r.height;
  const wall_ids=[];
  for(const w of ir?.walls||[]){
    const p0=Core.worldToSourcePx(ir.coordinate_frame,w.start),p1=Core.worldToSourcePx(ir.coordinate_frame,w.end);
    if(inside(p0)&&inside(p1))wall_ids.push(w.id);
  }
  return{rect:r,wall_ids};
}

function appendCorrection(ir,edit){const out=clone(ir);(out.edits||(out.edits=[])).push(clone(edit));return out}
function deleteWallsById(ir,ids){
  const wanted=new Set(ids||[]),removed=[];
  for(const w of ir?.walls||[])if(wanted.has(w.id))removed.push(wallEvidence(ir,w));
  let out=clone(ir);
  out.walls=(out.walls||[]).filter(w=>!wanted.has(w.id));
  if(removed.length)(out.edits||(out.edits=[])).push({op:'delete_walls',removed});
  return out;
}
function correctedId(e){return e?.replacement?.wall_id||`wall-corrected-${String(e?.original?.wall_id||'wall').replace(/[^a-zA-Z0-9_-]/g,'_')}`}
function moveWallPx(ir,wallId,startPx,endPx,opts={}){
  const out=clone(ir),idx=(out.walls||[]).findIndex(w=>w.id===wallId);
  if(idx<0)return out;
  const original=wallEvidence(out,out.walls[idx]),old=out.walls[idx];
  const replacement={wall_id:`wall-corrected-${Date.now().toString(36)}`,start_px:{...startPx},end_px:{...endPx},source:'manual'};
  out.walls.splice(idx,1,{...old,id:replacement.wall_id,start:Core.sourcePxToWorld(out.coordinate_frame,startPx),end:Core.sourcePxToWorld(out.coordinate_frame,endPx),source:'manual',confidence:1,corrected_from:original});
  (out.edits||(out.edits=[])).push({op:'move_wall',original,replacement,mode:opts.mode||'move'});
  return out;
}
function applyDeleteEvidence(ir,edit){
  const out=clone(ir),drop=new Set();
  for(const e of edit.removed||[]){const m=matchWallByEvidence(out,e);if(m)drop.add(m.index)}
  out.walls=(out.walls||[]).filter((_,i)=>!drop.has(i));
  return out;
}
function applyMoveEvidence(ir,edit){
  const out=clone(ir),m=matchWallByEvidence(out,edit.original||{});
  let template=m?.wall||null;
  if(m)out.walls.splice(m.index,1);
  const rp=edit.replacement;
  if(!rp?.start_px||!rp?.end_px)return out;
  const g=out.geometry||{};
  out.walls.push({
    id:correctedId(edit),
    start:Core.sourcePxToWorld(out.coordinate_frame,rp.start_px),
    end:Core.sourcePxToWorld(out.coordinate_frame,rp.end_px),
    thickness:Number(template?.thickness||g.wall_thickness_m||.12),height:Number(template?.height||g.wall_height_m||2.7),
    confidence:1,source:'manual',corrected_from:clone(edit.original||{})
  });
  return out;
}
function replayCorrections(base,edits=[]){
  let out=clone(base),journal=[];
  for(const e of edits||[]){
    if(!MANUAL_OPS.has(e?.op))continue;
    if(e.op==='add_wall'&&e.start_px&&e.end_px){
      const before=(out.edits||[]).length;
      out=Core.addWallPx(out,e.start_px,e.end_px,{orthogonal:e.orthogonal!==false});
      out.edits=(out.edits||[]).slice(0,before);
    }else if(e.op==='erase_segments'&&e.stroke_points){
      const before=(out.edits||[]).length;
      out=Core.eraseStrokePx(out,e.stroke_points,e.radius_px||10);
      out.edits=(out.edits||[]).slice(0,before);
    }else if(e.op==='delete_walls')out=applyDeleteEvidence(out,e);
    else if(e.op==='move_wall')out=applyMoveEvidence(out,e);
    journal.push(clone(e));
  }
  out.edits=(out.edits||[]).filter(e=>!MANUAL_OPS.has(e.op)).concat(journal);
  return out;
}
function extractCorrectionJournal(ir){return(ir?.edits||[]).filter(e=>MANUAL_OPS.has(e?.op)).map(clone)}
function createCorrectionSession(initialIr=null){
  let journal=extractCorrectionJournal(initialIr);
  return{
    list:()=>journal.map(clone),
    clear:()=>{journal=[]},
    capture:ir=>{const incoming=extractCorrectionJournal(ir);if(incoming.length)journal=incoming;return journal.map(clone)},
    replace:edits=>{journal=(edits||[]).filter(e=>MANUAL_OPS.has(e?.op)).map(clone);return journal.map(clone)},
    rebase:base=>replayCorrections(base,journal)
  };
}

const api={version:'0.7.0',MANUAL_OPS,createEditableDocument,wallEvidence,evidenceDistance,matchWallByEvidence,selectWallNearPx,selectWallsInRectPx,deleteWallsById,moveWallPx,replayCorrections,rebaseCorrections:replayCorrections,extractCorrectionJournal,createCorrectionSession};
global.LayoutLibEditor=api;
// Compatibility: replay through the correction-aware library path.
Core.replayEdits=(base,edits=[])=>replayCorrections(base,edits);
})(window);
