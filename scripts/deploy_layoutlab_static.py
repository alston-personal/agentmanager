#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'index.html': ROOT / 'web_assets/layoutlab_v0_5.html',
    'layoutlib-browser-v0.5.js': ROOT / 'web_assets/layoutlib-browser-v0.5.js',
}
TARGET_DIR = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')

HOTFIX = r'''<script>
(()=>{
const L=window.LayoutLibBrowser;if(!L||L.version!=='0.6.0')return;
const clone=v=>JSON.parse(JSON.stringify(v)),clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
L.createEditableDocument=(W,H,o={})=>{W=Math.max(1,Math.round(W));H=Math.max(1,Math.round(H));const m=Math.max(.000001,Number(o.meters_per_pixel||.02)),r=o.analysis_region_px||{x:0,y:0,width:W,height:H};return{version:'0.6',units:'m',image_width_px:W,image_height_px:H,meters_per_pixel:m,coordinate_frame:{anchor_px:{x:r.x||0,y:r.y||0},anchor_world_m:{x:0,y:0},meters_per_pixel:m,rotation_deg:0,image_y_axis:'down'},analysis_region_px:clone(r),scale_calibration:o.scale_calibration||null,detection:{threshold:clamp(Number(o.threshold??128),0,255),min_wall_length_px:Number(o.min_wall_length_px||16),max_wall_thickness_px:Number(o.max_wall_thickness_px||16),state:'uncommitted'},geometry:{wall_height_m:Number(o.wall_height_m||2.7),wall_thickness_m:Number(o.wall_thickness_m||.12),floor_enabled:o.floor_enabled!==false,floor_thickness_m:.15},walls:[],edits:[],profile_prediction:o.profile_prediction||null,document_state:'editable_before_analysis'}};
const wp=(ir,w)=>({a:L.worldToSourcePx(ir.coordinate_frame,w.start),b:L.worldToSourcePx(ir.coordinate_frame,w.end)}),inr=(p,r)=>p.x>=r.x&&p.x<=r.x+r.width&&p.y>=r.y&&p.y<=r.y+r.height;
L.selectWallsInRectPx=(ir,a,b)=>{const r={x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),width:Math.abs(b.x-a.x),height:Math.abs(b.y-a.y)},wall_ids=[];for(const w of ir.walls||[]){const p=wp(ir,w);if(inr(p.a,r)&&inr(p.b,r))wall_ids.push(w.id)}return{rect:r,wall_ids}};
L.selectWallNearPx=(ir,p,rad=8)=>{let id=null,bd=1e9;for(const w of ir.walls||[]){const q=wp(ir,w),vx=q.b.x-q.a.x,vy=q.b.y-q.a.y,l=vx*vx+vy*vy||1,t=clamp(((p.x-q.a.x)*vx+(p.y-q.a.y)*vy)/l,0,1),x=q.a.x+t*vx,y=q.a.y+t*vy,d=Math.hypot(p.x-x,p.y-y);if(d<bd){bd=d;id=w.id}}return bd<=rad?id:null};
L.deleteWallsById=(ir,ids)=>{const o=clone(ir),s=new Set(ids||[]),removed=[];o.walls=(o.walls||[]).filter(w=>{if(!s.has(w.id))return true;removed.push({wall_id:w.id});return false});if(removed.length)(o.edits||(o.edits=[])).push({op:'delete_walls',removed});return o};
const oldReplay=L.replayEdits;L.replayEdits=(base,edits=[])=>{let o=oldReplay(base,edits.filter(e=>e.op!=='delete_walls'));for(const e of edits)if(e.op==='delete_walls')o=L.deleteWallsById(o,(e.removed||[]).map(x=>x.wall_id));return o};
const tb=document.querySelector('.work .panel .toolbar .buttons');if(!tb)return;
const sb=document.createElement('button');sb.id='selectWall';sb.className='secondary';sb.textContent='▭ 選取';tb.insertBefore(sb,document.getElementById('undo'));
const db=document.createElement('button');db.id='deleteSelected';db.className='secondary dangerGhost';db.textContent='刪除選取';db.disabled=true;tb.insertBefore(db,document.getElementById('undo'));
let sel=new Set(),box=null;
const oldManual=manualEdits;manualEdits=()=>{const x=(currentIr?.edits||[]).filter(e=>['add_wall','erase_segments','delete_walls'].includes(e.op));return x.length?x:oldManual()};
const oldSet=setMode;setMode=m=>{if(m!=='select'){sb.classList.remove('active');return oldSet(m)}mode=m;eraseImpact=null;['addWall','eraseWall','roiMode','calibrate','selectWall'].forEach(id=>document.getElementById(id)?.classList.remove('active'));sb.classList.add('active');document.getElementById('modePill').textContent='選取';render2d()};
sb.onclick=()=>setMode(mode==='select'?'none':'select');db.onclick=()=>{if(!currentIr||!sel.size)return;saveHistory();applyIr(L.deleteWallsById(currentIr,[...sel]));sel.clear();db.disabled=true;render2d()};
const oldRender=render2d;render2d=()=>{oldRender();const ir=displayIr();if(ir){dctx.lineCap='round';for(const w of ir.walls||[]){if(!sel.has(w.id))continue;const a=L.worldToSourcePx(ir.coordinate_frame,w.start),b=L.worldToSourcePx(ir.coordinate_frame,w.end);dctx.strokeStyle='rgba(0,190,255,.78)';dctx.lineWidth=Math.max(9,w.thickness/ir.meters_per_pixel+7);dctx.beginPath();dctx.moveTo(a.x,a.y);dctx.lineTo(b.x,b.y);dctx.stroke();dctx.strokeStyle='#fff';dctx.lineWidth=2;dctx.stroke()}}if(box){dctx.fillStyle='rgba(0,160,220,.1)';dctx.strokeStyle='#009bd0';dctx.lineWidth=2;dctx.setLineDash([7,5]);dctx.fillRect(box.x,box.y,box.width,box.height);dctx.strokeRect(box.x,box.y,box.width,box.height);dctx.setLineDash([])}};
const od=display.onpointerdown,om=display.onpointermove,ou=display.onpointerup;display.onpointerdown=e=>{if(mode!=='select')return od(e);dragStart=pnt(e);stroke=[dragStart];box={x:dragStart.x,y:dragStart.y,width:0,height:0};display.setPointerCapture?.(e.pointerId);e.preventDefault()};display.onpointermove=e=>{if(mode!=='select'||!dragStart)return om(e);const p=pnt(e);stroke=[p];box={x:Math.min(dragStart.x,p.x),y:Math.min(dragStart.y,p.y),width:Math.abs(p.x-dragStart.x),height:Math.abs(p.y-dragStart.y)};render2d();e.preventDefault()};display.onpointerup=e=>{if(mode!=='select'||!dragStart)return ou(e);const p=pnt(e),append=e.ctrlKey||e.metaKey,d=Math.hypot(p.x-dragStart.x,p.y-dragStart.y);if(!append)sel.clear();if(d<5){const id=L.selectWallNearPx(displayIr(),p,Math.max(8,display.width/130));if(id){if(append&&sel.has(id))sel.delete(id);else sel.add(id)}}else for(const id of L.selectWallsInRectPx(displayIr(),dragStart,p).wall_ids)sel.add(id);dragStart=null;stroke=[];box=null;db.disabled=!sel.size;status.textContent=sel.size?`已選取 ${sel.size} 面牆；Ctrl/Cmd 可追加或切換，按「刪除選取」。`:'未選取牆';render2d();e.preventDefault()};
const of=file.onchange;file.onchange=async e=>{await of(e);currentIr=L.createEditableDocument(source.width,source.height,opts());baseIr=null;history=[];future=[];sel.clear();applyIr(currentIr);sb.disabled=false;db.disabled=true;status.textContent='圖片已載入：可直接補牆；按「分析」再加入自動偵測牆。'};
document.getElementById('resetView').onclick=()=>{view={yaw:0,pitch:0,zoom:1};render3d()};
})();
</script>'''


def _identity(name: str, data: bytes) -> None:
    if name == 'index.html':
        required = [b'<title>Layout Lab | Milkcat Studio</title>', b'LayoutLib Browser Adapter v0.6', b'3D \xe5\x8d\xb3\xe6\x99\x82\xe5\xb0\x8d\xe7\x85\xa7', b'layoutlib.profile.samples.v1', b'previewEraseStrokePx']
        if not all(x in data for x in required):
            raise SystemExit('html source asset failed v0.6 identity check')
    elif name.endswith('.js'):
        required = [b'LayoutLib Browser Adapter v0.6.0', b"version:'0.6.0'", b'previewEraseStrokePx', b'extractProfileFeatures', b'predictProfileParameters', b'makeLearningObservation', b'replayEdits']
        if not all(x in data for x in required):
            raise SystemExit('browser library asset failed v0.6 identity check')


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(TARGET_DIR, 0o755)
    artifacts = {}
    for name, source in SOURCES.items():
        if not source.is_file():
            raise SystemExit(f'missing source asset: {source}')
        data = source.read_bytes()
        _identity(name, data)
        if name == 'index.html':
            text = data.decode('utf-8')
            if 'deleteSelected' not in text:
                text = text.replace('</body>', HOTFIX + '\n</body>')
            data = text.encode('utf-8')
        target = TARGET_DIR / name
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_bytes(data)
        os.chmod(tmp, 0o644)
        tmp.replace(target)
        os.chmod(target, 0o644)
        artifacts[name] = {'source': str(source), 'target': str(target), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    print(json.dumps({'ok': True, 'directory': str(TARGET_DIR), 'directory_mode': '0755', 'file_mode': '0644', 'mode': 'layoutlib-v0.6-demo-hotfix', 'artifacts': artifacts}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
