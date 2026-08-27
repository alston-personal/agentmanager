/* Layout Lab v0.7 release overlay
 * Keeps the v0.6 parser core compatible while presenting the v0.7 product
 * identity and making selected-wall deletion survive regenerated wall ids.
 */
(()=>{
'use strict';
const L=window.LayoutLibBrowser;
if(!L)return;
const clone=v=>JSON.parse(JSON.stringify(v));
const px=(ir,w)=>({
  start_px:L.worldToSourcePx(ir.coordinate_frame,w.start),
  end_px:L.worldToSourcePx(ir.coordinate_frame,w.end)
});
const dist=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const evidenceDistance=(ir,w,e)=>{
  if(!e?.start_px||!e?.end_px)return Infinity;
  const p=px(ir,w);
  const direct=dist(p.start_px,e.start_px)+dist(p.end_px,e.end_px);
  const reverse=dist(p.start_px,e.end_px)+dist(p.end_px,e.start_px);
  return Math.min(direct,reverse);
};
const evidenceFor=(ir,w)=>{
  const p=px(ir,w);
  return {wall_id:w.id,start_px:p.start_px,end_px:p.end_px,source:w.source||null};
};
function removeByEvidence(ir,removed){
  const out=clone(ir),walls=[...(out.walls||[])],drop=new Set();
  for(const e of removed||[]){
    let idx=walls.findIndex((w,i)=>!drop.has(i)&&w.id===e.wall_id);
    if(idx<0&&e.start_px&&e.end_px){
      let best=-1,bestD=Infinity;
      walls.forEach((w,i)=>{
        if(drop.has(i))return;
        if(e.source&&w.source&&e.source!==w.source)return;
        const d=evidenceDistance(out,w,e);
        if(d<bestD){bestD=d;best=i}
      });
      if(best>=0&&bestD<=16)idx=best;
    }
    if(idx>=0)drop.add(idx);
  }
  out.walls=walls.filter((_,i)=>!drop.has(i));
  return out;
}
L.deleteWallsById=(ir,ids)=>{
  const out=clone(ir),wanted=new Set(ids||[]),removed=[];
  for(const w of out.walls||[])if(wanted.has(w.id))removed.push(evidenceFor(out,w));
  const next=removeByEvidence(out,removed);
  if(removed.length)(next.edits||(next.edits=[])).push({op:'delete_walls',removed});
  return next;
};
const replayBeforeV07=L.replayEdits;
L.replayEdits=(base,edits=[])=>{
  let out=replayBeforeV07(base,edits.filter(e=>e.op!=='delete_walls'));
  for(const e of edits)if(e.op==='delete_walls'){
    out=removeByEvidence(out,e.removed||[]);
    (out.edits||(out.edits=[])).push(clone(e));
  }
  return out;
};

/*
 * v0.7.4 fixes the actual button wiring.
 * The selection Set lives inside the v0.6 hotfix IIFE, so an external overlay
 * cannot replace button.onclick and still read `sel`. Doing that caused a
 * ReferenceError on click, which looked like a dead button. Instead, keep the
 * original onclick closure (which owns `sel`) and use a capture listener to
 * make currentIr equal to the exact displayed IR before that onclick runs.
 */
function bindDisplayedIrDelete(){
  const button=document.getElementById('deleteSelected');
  if(!button||typeof displayIr!=='function'||button.dataset.v07DeleteBound==='1')return false;
  button.dataset.v07DeleteBound='1';
  let beforeCount=null;
  button.addEventListener('click',()=>{
    const shown=displayIr();
    if(!shown)return;
    beforeCount=(shown.walls||[]).length;
    currentIr=clone(shown);
    previewIr=null;
    detectionDirty=false;
  },true);
  button.addEventListener('click',()=>{
    Promise.resolve().then(()=>{
      if(beforeCount===null||!currentIr)return;
      const after=(currentIr.walls||[]).length;
      if(after<beforeCount){
        status.textContent=`已刪除 ${beforeCount-after} 面牆。`;
      }
      beforeCount=null;
    });
  });
  return true;
}

function labelV07(){
  const sub=document.querySelector('header .sub');
  if(sub)sub.textContent='Layout Lab v0.7：2D / 3D 同屏、可編輯 Spatial IR、修正成本學習，以及 AgentOS Capability closed loop。';
  const badge=document.querySelector('header .badge');
  if(badge)badge.textContent='Layout Lab v0.7 · AgentOS closed loop';
  document.querySelectorAll('.compactTitle').forEach(el=>{
    if(/v0\.6\s+Learning contract/i.test(el.textContent||''))el.textContent='v0.7 Capability learning contract';
  });
}
labelV07();
bindDisplayedIrDelete();
window.LayoutLabV07Release={version:'0.7.4',robustDelete:true,displayedIrDelete:true,labelV07,bindDisplayedIrDelete};
})();
