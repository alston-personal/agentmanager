/* Layout Lab release presentation/interaction overlay.
 * UI only: no Spatial IR mutation, correction replay, or evidence semantics.
 */
(()=>{
'use strict';
const RELEASE='0.7.9';

function bindDeleteKey(){
  const isTypingTarget=t=>{
    if(!t)return false;
    if(t instanceof HTMLTextAreaElement || t.isContentEditable)return true;
    if(!(t instanceof HTMLInputElement))return false;
    const type=(t.type||'text').toLowerCase();
    return !['file','button','checkbox','radio','range','submit','reset'].includes(type);
  };
  document.addEventListener('keydown',e=>{
    if(!(e.key==='Delete'||e.code==='Delete'))return;
    if(isTypingTarget(e.target))return;
    const button=document.getElementById('deleteSelected');
    if(!button||button.disabled)return;
    e.preventDefault();button.click();
  },true);
}

function enable2dPanZoom(){
  const stage=document.querySelector('.stage'),canvas=document.getElementById('display');
  if(!stage||!canvas)return false;
  stage.style.overflow='auto';canvas.style.maxWidth='none';canvas.style.transformOrigin='0 0';
  let zoom2d=1,space=false,panning=false,lastX=0,lastY=0;
  const fitScale=()=>canvas.width>0?Math.min(1,Math.max(.05,(stage.clientWidth-2)/canvas.width)):1;
  const apply=()=>{const s=fitScale()*zoom2d;if(canvas.width>0&&canvas.height>0){canvas.style.width=`${Math.max(1,canvas.width*s)}px`;canvas.style.height=`${Math.max(1,canvas.height*s)}px`}};
  const reset=()=>{zoom2d=1;stage.scrollLeft=0;stage.scrollTop=0;stage.style.cursor='';requestAnimationFrame(apply)};
  document.getElementById('file')?.addEventListener('change',()=>setTimeout(reset,0));window.addEventListener('resize',apply);
  stage.addEventListener('wheel',e=>{if(!canvas.width)return;e.preventDefault();const rect=stage.getBoundingClientRect(),x=e.clientX-rect.left+stage.scrollLeft,y=e.clientY-rect.top+stage.scrollTop,old=zoom2d;zoom2d=Math.max(.2,Math.min(8,zoom2d*(e.deltaY<0?1.12:1/1.12)));if(old===zoom2d)return;const ratio=zoom2d/old;apply();stage.scrollLeft=x*ratio-(e.clientX-rect.left);stage.scrollTop=y*ratio-(e.clientY-rect.top)},{passive:false});
  document.addEventListener('keydown',e=>{if(e.code==='Space'&&!e.repeat)space=true},true);document.addEventListener('keyup',e=>{if(e.code==='Space')space=false},true);
  stage.addEventListener('contextmenu',e=>{if(zoom2d>1)e.preventDefault()});
  stage.addEventListener('pointerdown',e=>{const rightPan=e.button===2&&zoom2d>1,aux=e.button===1||(e.button===0&&space);if(!(rightPan||aux))return;panning=true;lastX=e.clientX;lastY=e.clientY;stage.style.cursor='grabbing';stage.setPointerCapture?.(e.pointerId);e.preventDefault();e.stopPropagation()},true);
  stage.addEventListener('pointermove',e=>{if(!panning)return;stage.scrollLeft-=e.clientX-lastX;stage.scrollTop-=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;e.preventDefault();e.stopPropagation()},true);
  const stop=e=>{if(!panning)return;panning=false;stage.style.cursor='';e?.preventDefault?.();e?.stopPropagation?.()};stage.addEventListener('pointerup',stop,true);stage.addEventListener('pointercancel',stop,true);setTimeout(apply,0);return true;
}

function fixViewerZoom(){
  const stage=document.getElementById('viewerStage'),canvas=document.getElementById('viewer'),zin=document.getElementById('zoomIn'),zout=document.getElementById('zoomOut');
  if(stage){stage.style.overflow='hidden';stage.style.contain='layout paint size'}if(canvas){canvas.style.position='absolute';canvas.style.inset='0';canvas.style.width='100%';canvas.style.height='100%'}
  const zoom=f=>{try{view.zoom=Math.max(.2,Math.min(8,Number(view.zoom||1)*f));render3d()}catch(err){console.error('LayoutLab viewer zoom failed',err)}};
  if(zin)zin.onclick=e=>{e.preventDefault();zoom(1.18)};if(zout)zout.onclick=e=>{e.preventDefault();zoom(1/1.18)};
}

function clarifyResetEdits(){const button=document.getElementById('clearEdits');if(!button)return;button.textContent='清除手動修正';button.title='移除補牆、擦牆、刪牆與移動牆等手動修正，回到本次自動分析結果。'}
function labelRelease(){
  const sub=document.querySelector('header .sub');if(sub)sub.textContent=`Layout Lab v${RELEASE}：LayoutLib 的 2D / 3D Spatial IR 編輯與 AgentOS Capability closed-loop demo。`;
  const badge=document.querySelector('header .badge');if(badge){badge.textContent=`v${RELEASE}`;badge.removeAttribute('title');badge.style.flex='0 0 auto';badge.style.fontWeight='800';badge.style.fontVariantNumeric='tabular-nums'}
  document.querySelectorAll('.compactTitle').forEach(el=>{if(/^v0\.(6|7(?:\.\d+)?)\s+(Learning|Capability learning) contract$/i.test(el.textContent||''))el.textContent=`v${RELEASE} Capability learning contract`});
  document.documentElement.dataset.layoutLabVersion=RELEASE;
}

labelRelease();bindDeleteKey();enable2dPanZoom();fixViewerZoom();clarifyResetEdits();
window.LayoutLabV07Release={version:RELEASE,uiOnly:true,deleteKey:true,fixedFrameZoom:true,twoDPanZoom:true,rightDragPan:true,compactVersionBadge:true};
})();
