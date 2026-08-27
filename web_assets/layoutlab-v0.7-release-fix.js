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
      // Endpoint-sum tolerance: 16 px allows modest parser regeneration drift.
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
 * Production bug fixed in v0.7.3:
 * the v0.6 selection hotfix selected walls from displayIr(), but its delete
 * button deleted from currentIr. While a Draft/preview was displayed those
 * are different documents, so the selected wall ids were absent from
 * currentIr and the click was a silent no-op. Deletion must operate on the
 * exact IR the user is looking at, then commit that result as currentIr.
 */
function bindDisplayedIrDelete(){
  const button=document.getElementById('deleteSelected');
  if(!button||typeof displayIr!=='function')return false;
  button.onclick=()=>{
    const shown=displayIr();
    if(!shown||!sel?.size)return;
    const before=(shown.walls||[]).length;
    const next=L.deleteWallsById(shown,[...sel]);
    const after=(next.walls||[]).length;
    if(after>=before){
      status.textContent='刪除失敗：選取牆未能對應目前顯示的 Spatial IR。';
      return;
    }
    saveHistory();
    // A user edit is a commit boundary: stop rendering an older Draft over it.
    previewIr=null;
    detectionDirty=false;
    applyIr(next);
    sel.clear();
    button.disabled=true;
    status.textContent=`已刪除 ${before-after} 面牆。`;
    render2d();
  };
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
window.LayoutLabV07Release={version:'0.7.3',robustDelete:true,displayedIrDelete:true,labelV07,bindDisplayedIrDelete};
})();
