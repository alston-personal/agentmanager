/* Layout Lab editor UI adapter v0.7.0
 * UI/input/rendering only. Spatial IR mutation semantics live in LayoutLibEditor.
 */
(()=>{
'use strict';
const E=window.LayoutLibEditor,L=window.LayoutLibBrowser;
if(!E||!L)return;
const correctionSession=E.createCorrectionSession();
const toolbar=document.querySelector('.work .panel .toolbar .buttons');
if(!toolbar)return;
const selectButton=document.createElement('button');selectButton.id='selectWall';selectButton.className='secondary';selectButton.textContent='▭ 選取';selectButton.style.display='none';toolbar.insertBefore(selectButton,document.getElementById('undo'));
const deleteButton=document.createElement('button');deleteButton.id='deleteSelected';deleteButton.className='secondary dangerGhost';deleteButton.textContent='刪除選取';deleteButton.disabled=true;toolbar.insertBefore(deleteButton,document.getElementById('undo'));
let selected=new Set(),box=null;

if(typeof manualEdits==='function')manualEdits=()=>correctionSession.list();
if(typeof applyIr==='function'){
  const baseApply=applyIr;
  applyIr=ir=>{correctionSession.capture(ir);return baseApply(ir)};
}
const clear=document.getElementById('clearEdits');
clear?.addEventListener('click',()=>correctionSession.clear(),true);
const input=document.getElementById('file');
input?.addEventListener('change',()=>{correctionSession.clear();selected.clear();deleteButton.disabled=true},true);

const baseSetMode=setMode;
setMode=m=>{
  if(m!=='select'){selectButton.classList.remove('active');return baseSetMode(m)}
  mode='select';eraseImpact=null;
  ['addWall','eraseWall','roiMode','calibrate','selectWall'].forEach(id=>document.getElementById(id)?.classList.remove('active'));
  selectButton.classList.add('active');document.getElementById('modePill').textContent='選取';render2d();
};
const enterSelect=()=>{if(!selectButton.disabled&&!selectButton.classList.contains('active'))selectButton.click()};
selectButton.onclick=()=>setMode(mode==='select'?'none':'select');
setTimeout(enterSelect,0);
input?.addEventListener('change',()=>setTimeout(enterSelect,0));

deleteButton.onclick=()=>{
  if(!selected.size)return;
  const shown=typeof displayIr==='function'?displayIr():currentIr;
  if(!shown)return;
  saveHistory();
  const next=E.deleteWallsById(shown,[...selected]);
  correctionSession.capture(next);
  if(typeof previewIr!=='undefined')previewIr=null;
  if(typeof detectionDirty!=='undefined')detectionDirty=false;
  applyIr(next);
  selected.clear();deleteButton.disabled=true;render2d();
};

const baseRender=render2d;
render2d=()=>{
  baseRender();const ir=displayIr();
  if(ir){dctx.lineCap='round';for(const w of ir.walls||[]){if(!selected.has(w.id))continue;const a=L.worldToSourcePx(ir.coordinate_frame,w.start),b=L.worldToSourcePx(ir.coordinate_frame,w.end);dctx.strokeStyle='rgba(0,190,255,.78)';dctx.lineWidth=Math.max(9,w.thickness/ir.meters_per_pixel+7);dctx.beginPath();dctx.moveTo(a.x,a.y);dctx.lineTo(b.x,b.y);dctx.stroke();dctx.strokeStyle='#fff';dctx.lineWidth=2;dctx.stroke()}}
  if(box){dctx.fillStyle='rgba(0,160,220,.1)';dctx.strokeStyle='#009bd0';dctx.lineWidth=2;dctx.setLineDash([7,5]);dctx.fillRect(box.x,box.y,box.width,box.height);dctx.strokeRect(box.x,box.y,box.width,box.height);dctx.setLineDash([])}
};

const down=display.onpointerdown,move=display.onpointermove,up=display.onpointerup;
display.onpointerdown=e=>{if(mode!=='select')return down(e);dragStart=pnt(e);stroke=[dragStart];box={x:dragStart.x,y:dragStart.y,width:0,height:0};display.setPointerCapture?.(e.pointerId);e.preventDefault()};
display.onpointermove=e=>{if(mode!=='select'||!dragStart)return move(e);const p=pnt(e);stroke=[p];box={x:Math.min(dragStart.x,p.x),y:Math.min(dragStart.y,p.y),width:Math.abs(p.x-dragStart.x),height:Math.abs(p.y-dragStart.y)};render2d();e.preventDefault()};
display.onpointerup=e=>{
  if(mode!=='select'||!dragStart)return up(e);
  const p=pnt(e),append=e.ctrlKey||e.metaKey,d=Math.hypot(p.x-dragStart.x,p.y-dragStart.y),ir=displayIr();
  if(!append)selected.clear();
  if(ir){if(d<5){const id=E.selectWallNearPx(ir,p,Math.max(8,display.width/130));if(id){if(append&&selected.has(id))selected.delete(id);else selected.add(id)}}else for(const id of E.selectWallsInRectPx(ir,dragStart,p).wall_ids)selected.add(id)}
  dragStart=null;stroke=[];box=null;deleteButton.disabled=!selected.size;
  status.textContent=selected.size?`已選取 ${selected.size} 面牆；Delete 可刪除。`:'未選取牆';render2d();e.preventDefault();
};

// File selection immediately exposes an automatic draft while keeping manual corrections separate.
if(typeof file!=='undefined'&&typeof file.onchange==='function'){
  const baseFileChange=file.onchange;
  file.onchange=async e=>{
    await baseFileChange(e);
    if(!bitmap)return;
    currentIr=E.createEditableDocument(source.width,source.height,opts());
    previewIr=analyzeRaw();detectionDirty=true;baseIr=null;history=[];future=[];
    correctionSession.clear();selected.clear();deleteButton.disabled=true;
    document.getElementById('draftPill').style.display='inline';
    document.getElementById('dirtyLabel').style.display='none';
    applyIr(currentIr);renderAll();enterSelect();
    status.textContent=`Draft：${(previewIr.walls||[]).length} 面候選牆 · Threshold ${previewIr.detection?.threshold ?? ''}；可直接選取與修正。`;
  };
}

// Re-analysis/drafts rebase library-owned correction journal over the new automatic base.
if(typeof withManual==='function')withManual=base=>{let out=correctionSession.rebase(base);if(currentIr?.geometry)out=L.setGeometry(out,currentIr.geometry);return out};

window.LayoutLabEditorUI={version:'0.7.0',correctionSession,selected};
})();
