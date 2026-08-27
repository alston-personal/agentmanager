/* Layout Lab v0.7 release overlay
 * Keeps the v0.6 parser core compatible while presenting the current v0.7
 * product patch identity and fixing production editor interaction semantics.
 */
(()=>{
'use strict';
const L=window.LayoutLibBrowser;
if(!L)return;
const RELEASE='0.7.6';
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

/* Keep manual corrections as an editor-owned overlay. Parser parameter drafts
 * may change the automatic base, but they must never erase or resurrect a
 * user's add/erase/delete corrections. */
const MANUAL_OPS=new Set(['add_wall','erase_segments','delete_walls']);
let durableManualEdits=[];
const extractManual=ir=>(ir?.edits||[]).filter(e=>MANUAL_OPS.has(e.op)).map(clone);
function installDurableManualLayer(){
  try{
    if(typeof currentIr!=='undefined')durableManualEdits=extractManual(currentIr);
    if(typeof manualEdits==='function'){
      manualEdits=()=>durableManualEdits.map(clone);
    }
    if(typeof applyIr==='function'){
      const beforeApply=applyIr;
      applyIr=ir=>{
        const incoming=extractManual(ir);
        if(incoming.length)durableManualEdits=incoming;
        return beforeApply(ir);
      };
    }
    const clear=document.getElementById('clearEdits');
    clear?.addEventListener('click',()=>{durableManualEdits=[]},true);
    return true;
  }catch(err){
    console.error('LayoutLab durable manual layer failed',err);
    return false;
  }
}

/* Keep the original selection closure that owns `sel`, but make its delete
 * handler operate on the exact IR currently displayed. */
function prepareDisplayedIrDelete(){
  const button=document.getElementById('deleteSelected');
  if(!button)return false;
  button.addEventListener('click',()=>{
    try{
      if(typeof displayIr!=='function')return;
      const shown=displayIr();
      if(!shown)return;
      if(typeof currentIr!=='undefined'&&shown!==currentIr){
        currentIr=clone(shown);
        if(typeof previewIr!=='undefined')previewIr=null;
        if(typeof detectionDirty!=='undefined')detectionDirty=false;
      }
    }catch(err){ console.error('LayoutLab delete preparation failed',err); }
  },true);
  return true;
}

/* Selection is the default idle tool. The old explicit selection button stays
 * as an implementation hook for the closure that owns `sel`, but is hidden. */
function enableDefaultSelection(){
  const selectButton=document.getElementById('selectWall');
  const displayCanvas=document.getElementById('display');
  if(!selectButton)return false;
  selectButton.style.display='none';
  const enter=()=>{
    if(selectButton.disabled)return;
    if(!selectButton.classList.contains('active'))selectButton.click();
  };
  setTimeout(enter,0);
  document.getElementById('file')?.addEventListener('change',()=>setTimeout(enter,0));
  displayCanvas?.addEventListener('pointerup',()=>{
    const add=document.getElementById('addWall'),erase=document.getElementById('eraseWall');
    if(add?.classList.contains('active')||erase?.classList.contains('active'))setTimeout(enter,0);
  });
  return true;
}

function bindDeleteKey(){
  document.addEventListener('keydown',e=>{
    if(!(e.key==='Delete'||e.code==='Delete'))return;
    const t=e.target;
    if(t && (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t.isContentEditable))return;
    const button=document.getElementById('deleteSelected');
    if(!button||button.disabled)return;
    e.preventDefault();
    button.click();
  },true);
}

/* 2D image navigation: wheel zooms the image/IR in-place; Space+left-drag or
 * middle-drag pans. Left drag without Space remains wall selection. */
function enable2dPanZoom(){
  const stage=document.querySelector('.stage');
  const canvas=document.getElementById('display');
  if(!stage||!canvas)return false;
  stage.style.overflow='auto';
  canvas.style.maxWidth='none';
  canvas.style.transformOrigin='0 0';
  let zoom2d=1,space=false,panning=false,lastX=0,lastY=0;
  const fitScale=()=>canvas.width>0?Math.min(1,Math.max(.05,(stage.clientWidth-2)/canvas.width)):1;
  const apply=()=>{
    const s=fitScale()*zoom2d;
    if(canvas.width>0&&canvas.height>0){
      canvas.style.width=`${Math.max(1,canvas.width*s)}px`;
      canvas.style.height=`${Math.max(1,canvas.height*s)}px`;
    }
  };
  const reset=()=>{zoom2d=1;stage.scrollLeft=0;stage.scrollTop=0;requestAnimationFrame(apply)};
  document.getElementById('file')?.addEventListener('change',()=>setTimeout(reset,0));
  window.addEventListener('resize',apply);
  stage.addEventListener('wheel',e=>{
    if(!canvas.width)return;
    e.preventDefault();
    const rect=stage.getBoundingClientRect();
    const x=e.clientX-rect.left+stage.scrollLeft;
    const y=e.clientY-rect.top+stage.scrollTop;
    const old=zoom2d;
    zoom2d=Math.max(.2,Math.min(8,zoom2d*(e.deltaY<0?1.12:1/1.12)));
    if(old===zoom2d)return;
    const ratio=zoom2d/old;
    apply();
    stage.scrollLeft=x*ratio-(e.clientX-rect.left);
    stage.scrollTop=y*ratio-(e.clientY-rect.top);
  },{passive:false});
  document.addEventListener('keydown',e=>{if(e.code==='Space'&&!e.repeat)space=true},true);
  document.addEventListener('keyup',e=>{if(e.code==='Space')space=false},true);
  stage.addEventListener('pointerdown',e=>{
    if(!(e.button===1||(e.button===0&&space)))return;
    panning=true;lastX=e.clientX;lastY=e.clientY;
    stage.setPointerCapture?.(e.pointerId);
    e.preventDefault();e.stopPropagation();
  },true);
  stage.addEventListener('pointermove',e=>{
    if(!panning)return;
    stage.scrollLeft-=e.clientX-lastX;stage.scrollTop-=e.clientY-lastY;
    lastX=e.clientX;lastY=e.clientY;
    e.preventDefault();e.stopPropagation();
  },true);
  const stop=e=>{if(!panning)return;panning=false;e?.preventDefault?.();e?.stopPropagation?.()};
  stage.addEventListener('pointerup',stop,true);
  stage.addEventListener('pointercancel',stop,true);
  setTimeout(apply,0);
  return true;
}

function fixViewerZoom(){
  const stage=document.getElementById('viewerStage');
  const canvas=document.getElementById('viewer');
  const zin=document.getElementById('zoomIn'),zout=document.getElementById('zoomOut');
  if(stage){stage.style.overflow='hidden';stage.style.contain='layout paint size';}
  if(canvas){canvas.style.position='absolute';canvas.style.inset='0';canvas.style.width='100%';canvas.style.height='100%';}
  const zoom=factor=>{
    try{
      view.zoom=Math.max(.2,Math.min(8,Number(view.zoom||1)*factor));
      render3d();
    }catch(err){ console.error('LayoutLab viewer zoom failed',err); }
  };
  if(zin)zin.onclick=e=>{e.preventDefault();zoom(1.18)};
  if(zout)zout.onclick=e=>{e.preventDefault();zoom(1/1.18)};
}

function clarifyResetEdits(){
  const button=document.getElementById('clearEdits');
  if(!button)return;
  button.textContent='清除手動修正';
  button.title='移除補牆、擦牆與刪牆等手動修正，回到本次自動分析的原始結果。';
}

function labelRelease(){
  const full=`Layout Lab v${RELEASE} · AgentOS closed loop`;
  const sub=document.querySelector('header .sub');
  if(sub)sub.textContent=`Layout Lab v${RELEASE}：2D / 3D 同屏、可編輯 Spatial IR、修正成本學習，以及 AgentOS Capability closed loop。`;
  const badge=document.querySelector('header .badge');
  if(badge){badge.textContent=full;badge.title=`完整版本：${RELEASE}`;}
  document.querySelectorAll('.compactTitle').forEach(el=>{
    if(/^v0\.(6|7(?:\.\d+)?)\s+(Learning|Capability learning) contract$/i.test(el.textContent||''))el.textContent=`v${RELEASE} Capability learning contract`;
  });
  document.documentElement.dataset.layoutLabVersion=RELEASE;
}

labelRelease();
installDurableManualLayer();
prepareDisplayedIrDelete();
enableDefaultSelection();
bindDeleteKey();
enable2dPanZoom();
fixViewerZoom();
clarifyResetEdits();
window.LayoutLabV07Release={version:RELEASE,robustDelete:true,displayedIrDelete:true,defaultSelection:true,deleteKey:true,fixedFrameZoom:true,twoDPanZoom:true,durableManualEdits:true,labelRelease};
})();
