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

function installSemanticOverlay(){
  if(typeof render2d!=='function'||typeof displayIr!=='function'||typeof dctx==='undefined')return false;
  const baseRender=render2d;
  const openingById=ir=>new Map((ir?.openings||[]).map(o=>[o.id,o]));
  const drawDoor=(o,d)=>{
    const a=o.start_px,b=o.end_px;if(!a||!b)return;
    const hinge=d.hinge==='end'?b:a,other=d.hinge==='end'?a:b;
    const vx=other.x-hinge.x,vy=other.y-hinge.y,len=Math.max(1,Math.hypot(vx,vy));
    const sign=d.swing_side==='negative_normal'?-1:1;
    const nx=-vy/len*sign,ny=vx/len*sign;
    const open={x:hinge.x+nx*len,y:hinge.y+ny*len};
    dctx.save();dctx.lineCap='round';dctx.lineJoin='round';
    dctx.strokeStyle='rgba(0,145,80,.95)';dctx.fillStyle='rgba(0,145,80,.95)';dctx.lineWidth=Math.max(3,display.width/350);
    dctx.beginPath();dctx.moveTo(a.x,a.y);dctx.lineTo(b.x,b.y);dctx.stroke();
    dctx.beginPath();dctx.moveTo(hinge.x,hinge.y);dctx.lineTo(open.x,open.y);dctx.stroke();
    const r=Math.max(4,display.width/230);dctx.beginPath();dctx.arc(hinge.x,hinge.y,r,0,Math.PI*2);dctx.fill();
    const startAngle=Math.atan2(other.y-hinge.y,other.x-hinge.x),endAngle=Math.atan2(open.y-hinge.y,open.x-hinge.x);
    dctx.setLineDash([5,4]);dctx.lineWidth=Math.max(2,display.width/500);dctx.beginPath();dctx.arc(hinge.x,hinge.y,len,startAngle,endAngle,sign<0);dctx.stroke();dctx.setLineDash([]);
    const m={x:(a.x+b.x)/2,y:(a.y+b.y)/2};dctx.font=`700 ${Math.max(11,display.width/80)}px system-ui`;dctx.fillStyle='#006a3b';dctx.fillText('門',m.x+5,m.y-5);dctx.restore();
  };
  const drawWindow=o=>{
    const a=o.start_px,b=o.end_px;if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,len=Math.max(1,Math.hypot(dx,dy)),nx=-dy/len*3,ny=dx/len*3;
    dctx.save();dctx.strokeStyle='rgba(0,105,210,.95)';dctx.lineWidth=Math.max(2,display.width/500);
    for(const s of[-1,1]){dctx.beginPath();dctx.moveTo(a.x+nx*s,a.y+ny*s);dctx.lineTo(b.x+nx*s,b.y+ny*s);dctx.stroke()}
    const m={x:(a.x+b.x)/2,y:(a.y+b.y)/2};dctx.font=`700 ${Math.max(11,display.width/80)}px system-ui`;dctx.fillStyle='#0759a8';dctx.fillText('窗',m.x+5,m.y-5);dctx.restore();
  };
  const drawUnknown=o=>{const a=o.start_px,b=o.end_px;if(!a||!b)return;dctx.save();dctx.strokeStyle='rgba(200,125,0,.9)';dctx.lineWidth=2;dctx.setLineDash([6,5]);dctx.beginPath();dctx.moveTo(a.x,a.y);dctx.lineTo(b.x,b.y);dctx.stroke();dctx.restore()};
  render2d=()=>{
    baseRender();const ir=displayIr();if(!ir)return;const byId=openingById(ir),claimed=new Set();
    for(const d of ir.doors||[]){const o=byId.get(d.opening_id);if(o){claimed.add(o.id);drawDoor(o,d)}}
    for(const w of ir.windows||[]){const o=byId.get(w.opening_id);if(o){claimed.add(o.id);drawWindow(o)}}
    for(const o of ir.openings||[])if(!claimed.has(o.id))drawUnknown(o);
  };
  const updateStatus=()=>{const ir=displayIr();if(!ir)return;const s=ir.semantic_summary||{};const walls=(ir.walls||[]).length,doors=(ir.doors||[]).length,windows=(ir.windows||[]).length,rooms=(ir.rooms||[]).length,openings=(ir.openings||[]).length;const el=document.getElementById('status');if(el&&document.getElementById('file')?.files?.length)el.textContent=`Draft：${walls} 牆 · ${doors} 門 · ${windows} 窗 · ${rooms} 房 · ${openings} openings · Token ${s.token_cost??0}`;};
  document.getElementById('file')?.addEventListener('change',()=>setTimeout(()=>{render2d();updateStatus()},80));
  document.getElementById('analyze')?.addEventListener('click',()=>setTimeout(()=>{render2d();updateStatus()},0));
  setTimeout(()=>{render2d();updateStatus()},0);return true;
}

function clarifyResetEdits(){const button=document.getElementById('clearEdits');if(!button)return;button.textContent='清除手動修正';button.title='移除補牆、擦牆、刪牆與移動牆等手動修正，回到本次自動分析結果。'}
function labelRelease(){
  const sub=document.querySelector('header .sub');if(sub)sub.textContent='Floor Plan → Spatial IR → 3D';
  const badge=document.querySelector('header .badge');if(badge){badge.textContent=`v${RELEASE}`;badge.removeAttribute('title');badge.style.flex='0 0 auto';badge.style.fontWeight='800';badge.style.fontVariantNumeric='tabular-nums'}
  document.querySelectorAll('.compactTitle').forEach(el=>{if(/^v0\.(6|7(?:\.\d+)?)\s+(Learning|Capability learning) contract$/i.test(el.textContent||''))el.textContent='Semantic IR';});
  document.documentElement.dataset.layoutLabVersion=RELEASE;
}

labelRelease();bindDeleteKey();enable2dPanZoom();fixViewerZoom();clarifyResetEdits();const semanticOverlay=installSemanticOverlay();
window.LayoutLabV07Release={version:RELEASE,uiOnly:true,deleteKey:true,fixedFrameZoom:true,twoDPanZoom:true,rightDragPan:true,compactVersionBadge:true,semanticOverlay};
})();
