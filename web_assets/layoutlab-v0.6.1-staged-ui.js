/* Layout Lab v0.6.1 staged UI integration — NOT loaded by production HTML.
 * Integration target: web_assets/layoutlab_v0_5.html after demo freeze is lifted.
 * Assumes current v0.6 closure variables/functions and LayoutLib v0.6.1 staged extension.
 */

// 1) PRE-ANALYSIS EDITING
// On image load, initialize a canonical empty editable IR immediately instead of currentIr=null.
function stageInitEditableDocument(){
  currentIr=LayoutLibBrowser.createEditableDocument(source.width,source.height,opts());
  baseIr=null;
  history=[];future=[];
  $('addWall').disabled=false;
  $('eraseWall').disabled=false; // useful after manual walls exist; harmless when empty
  $('selectWall').disabled=false;
  applyIr(currentIr);
  status.textContent='圖片已載入：可直接補牆；自動牆可按「分析」產生。';
}

// Preserve pre-analysis manual edits when analysis is first committed.
function stageManualEdits(){
  return(currentIr?.edits||[]).filter(e=>['add_wall','erase_segments','delete_walls'].includes(e.op));
}

// 2) RECTANGLE / CTRL MULTI-SELECTION
let selectedWallIds=new Set(),selectionBox=null;
function stageSelectionToolbar(){
  // Expected HTML additions near 補牆/擦牆:
  // <button id="selectWall" class="secondary">▭ 選取</button>
  // <button id="deleteSelected" class="secondary dangerGhost" disabled>刪除選取</button>
}
function stageSetSelection(ids,append=false){
  if(!append)selectedWallIds.clear();
  for(const id of ids||[]) selectedWallIds.add(id);
  $('deleteSelected').disabled=!selectedWallIds.size;
  render2d();
  status.textContent=selectedWallIds.size?`已選取 ${selectedWallIds.size} 面牆；Ctrl 可追加，按「刪除選取」一次刪除。`:'未選取牆。';
}
function stageSelectByBox(start,end,append=false){
  const hit=LayoutLibBrowser.selectWallsInRectPx(displayIr(),start,end,{mode:'contain'});
  stageSetSelection(hit.wall_ids,append);
}
function stageSelectByCtrlClick(p,append=true){
  const id=LayoutLibBrowser.selectWallNearPx(displayIr(),p,Math.max(8,display.width/130));
  if(!id)return;
  if(append&&selectedWallIds.has(id))selectedWallIds.delete(id);else{if(!append)selectedWallIds.clear();selectedWallIds.add(id)}
  $('deleteSelected').disabled=!selectedWallIds.size;render2d();
}
function stageDeleteSelected(){
  if(!currentIr||!selectedWallIds.size)return;
  saveHistory();
  applyIr(LayoutLibBrowser.deleteWallsById(currentIr,[...selectedWallIds]));
  selectedWallIds.clear();$('deleteSelected').disabled=true;
}

// Render integration: after normal wall rendering, selected walls are cyan/white highlighted.
function stageRenderSelectionOverlay(ir){
  if(!ir||!selectedWallIds.size)return;
  dctx.lineCap='round';
  for(const w of ir.walls){if(!selectedWallIds.has(w.id))continue;const a=LayoutLibBrowser.worldToSourcePx(ir.coordinate_frame,w.start),b=LayoutLibBrowser.worldToSourcePx(ir.coordinate_frame,w.end),px=Math.max(8,w.thickness/ir.meters_per_pixel+7);dctx.strokeStyle='rgba(0,190,255,.76)';dctx.lineWidth=px;dctx.beginPath();dctx.moveTo(a.x,a.y);dctx.lineTo(b.x,b.y);dctx.stroke();dctx.strokeStyle='#fff';dctx.lineWidth=2;dctx.stroke();}
  if(selectionBox){dctx.fillStyle='rgba(0,160,220,.10)';dctx.strokeStyle='#009bd0';dctx.lineWidth=2;dctx.setLineDash([7,5]);dctx.fillRect(selectionBox.x,selectionBox.y,selectionBox.width,selectionBox.height);dctx.strokeRect(selectionBox.x,selectionBox.y,selectionBox.width,selectionBox.height);dctx.setLineDash([])}
}

// Pointer integration for mode==='select': drag rectangle; Ctrl/Cmd click toggles/adds one wall.
function stageSelectionPointerDown(e){
  if(mode!=='select')return false;
  dragStart=pnt(e);stroke=[dragStart];selectionBox={x:dragStart.x,y:dragStart.y,width:0,height:0};return true;
}
function stageSelectionPointerMove(e){
  if(mode!=='select'||!dragStart)return false;
  const p=pnt(e);stroke=[p];selectionBox={x:Math.min(dragStart.x,p.x),y:Math.min(dragStart.y,p.y),width:Math.abs(p.x-dragStart.x),height:Math.abs(p.y-dragStart.y)};render2d();return true;
}
function stageSelectionPointerUp(e){
  if(mode!=='select'||!dragStart)return false;
  const end=pnt(e),dist=Math.hypot(end.x-dragStart.x,end.y-dragStart.y),append=e.ctrlKey||e.metaKey;
  if(dist<5)stageSelectByCtrlClick(end,append);else stageSelectByBox(dragStart,end,append);
  dragStart=null;stroke=[];selectionBox=null;render2d();return true;
}

// 3) RESET VIEW = 2D PLAN-ALIGNED TOP VIEW
// Current projection maps XY plane through yaw/pitch. pitch=0 gives a plan view; yaw=0 keeps +X right and +Y down,
// matching the source image coordinate frame image_y_axis:'down'. This is the correct reset for 2D comparison.
function stageResetViewTo2D(){
  view={yaw:0,pitch:0,zoom:1};
  render3d();
}

// Suggested post-demo wiring:
// $('selectWall').onclick=()=>setMode(mode==='select'?'none':'select');
// $('deleteSelected').onclick=stageDeleteSelected;
// $('resetView').onclick=stageResetViewTo2D;
// setMode() should include selectWall and mode label '選取'.
// render2d() should call stageRenderSelectionOverlay(ir) after normal walls.
// file.onchange should call stageInitEditableDocument() after profile prediction + source setup.
