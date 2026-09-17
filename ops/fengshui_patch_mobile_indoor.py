from pathlib import Path

p = Path('components/Floorplan3DViewer.tsx')
s = p.read_text()

if 'function AxisJoystick(' in s:
    print('mobile indoor patch already applied')
    raise SystemExit(0)

def rep(old: str, new: str) -> None:
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'expected one match, got {n}: {old[:120]!r}')
    s = s.replace(old, new, 1)

rep("import './floorplan-viewer.css';", "import './floorplan-viewer.css';\nimport './indoor-joystick.css';")

marker = "export default function Floorplan3DViewer({"
joystick = r'''function AxisJoystick({axis,label,onValue}:{axis:'vertical'|'horizontal';label:string;onValue:(value:number)=>void}) {
  const base=useRef<HTMLDivElement>(null),active=useRef(false),[offset,setOffset]=useState({x:0,y:0});
  const reset=()=>{active.current=false;setOffset({x:0,y:0});onValue(0);};
  const apply=(e:React.PointerEvent<HTMLDivElement>)=>{
    const el=base.current;if(!el)return;const r=el.getBoundingClientRect(),radius=Math.max(24,Math.min(r.width,r.height)*.34);
    let dx=e.clientX-(r.left+r.width/2),dy=e.clientY-(r.top+r.height/2);
    if(axis==='vertical')dx=0;else dy=0;
    const len=Math.hypot(dx,dy);if(len>radius){dx=dx/len*radius;dy=dy/len*radius;}
    setOffset({x:dx,y:dy});const value=axis==='vertical'?-dy/radius:dx/radius;onValue(Math.max(-1,Math.min(1,value)));
  };
  return <div className="fv-stick-wrap" aria-label={label}>
    <div ref={base} className={`fv-stick-base ${active.current?'is-active':''}`}
      onPointerDown={e=>{e.preventDefault();e.stopPropagation();active.current=true;e.currentTarget.setPointerCapture(e.pointerId);apply(e);}}
      onPointerMove={e=>{if(active.current){e.preventDefault();apply(e);}}}
      onPointerUp={e=>{try{e.currentTarget.releasePointerCapture(e.pointerId);}catch{}reset();}}
      onPointerCancel={reset} onLostPointerCapture={reset}>
      <div className="fv-stick-knob" style={{'--stick-x':`${offset.x}px`,'--stick-y':`${offset.y}px`} as React.CSSProperties}/>
    </div>
    <span className="fv-stick-label">{label}</span>
  </div>;
}

'''
rep(marker, joystick + marker)

rep(
    "  const mount=useRef<HTMLDivElement>(null),engine=useRef<any>(null),live=useRef<any>({});\n  const keys=useRef(new Set<string>()),pad=useRef({forward:0,right:0}),look=useRef({yaw:0,pitch:0});",
    "  const mount=useRef<HTMLDivElement>(null),viewer=useRef<HTMLElement>(null),engine=useRef<any>(null),live=useRef<any>({});\n  const keys=useRef(new Set<string>()),pad=useRef({forward:0,right:0}),drive=useRef({forward:0,turn:0}),look=useRef({yaw:0,pitch:0});"
)
rep(
    "  const [selectedPhotoIdx,setSelectedPhotoIdx]=useState<number|null>(null);",
    "  const [selectedPhotoIdx,setSelectedPhotoIdx]=useState<number|null>(null);\n  const [immersive,setImmersive]=useState(false),[portrait,setPortrait]=useState(false);"
)
rep(
    "    const clear=()=>{keys.current.clear();pad.current={forward:0,right:0};dragging=false;};",
    "    const clear=()=>{keys.current.clear();pad.current={forward:0,right:0};drive.current={forward:0,turn:0};dragging=false;};"
)

old_tick = r'''      if(live.current.mode==='indoor'&&live.current.nav){
        const f=Number(keys.current.has('KeyW')||keys.current.has('ArrowUp'))-Number(keys.current.has('KeyS')||keys.current.has('ArrowDown'))+pad.current.forward;
        const r=Number(keys.current.has('KeyD')||keys.current.has('ArrowRight'))-Number(keys.current.has('KeyA')||keys.current.has('ArrowLeft'))+pad.current.right;
        const delta=walkingDelta(Math.sign(f),Math.sign(r),look.current.yaw,dt);
        const p=moveWithinFloor(live.current.nav,{x:camera.position.x,y:camera.position.z},delta);camera.position.set(p.x,1.5,p.y);
        const {yaw,pitch}=look.current;camera.lookAt(p.x+Math.sin(yaw)*Math.cos(pitch),1.5+Math.sin(pitch),p.y-Math.cos(yaw)*Math.cos(pitch));
      }else controls.update();'''
new_tick = r'''      if(live.current.mode==='indoor'&&live.current.nav){
        const keyboardF=Number(keys.current.has('KeyW')||keys.current.has('ArrowUp'))-Number(keys.current.has('KeyS')||keys.current.has('ArrowDown'));
        const keyboardR=Number(keys.current.has('KeyD'))-Number(keys.current.has('KeyA'));
        const keyTurn=Number(keys.current.has('ArrowRight'))-Number(keys.current.has('ArrowLeft'));
        const turn=Math.max(-1,Math.min(1,drive.current.turn+keyTurn));
        look.current.yaw+=turn*1.9*Math.min(.05,Math.max(0,dt));
        const f=Math.max(-1,Math.min(1,keyboardF+pad.current.forward+drive.current.forward));
        const r=Math.max(-1,Math.min(1,keyboardR+pad.current.right));
        const delta=walkingDelta(f,r,look.current.yaw,dt);
        const p=moveWithinFloor(live.current.nav,{x:camera.position.x,y:camera.position.z},delta);camera.position.set(p.x,1.5,p.y);
        const {yaw,pitch}=look.current;camera.lookAt(p.x+Math.sin(yaw)*Math.cos(pitch),1.5+Math.sin(pitch),p.y-Math.cos(yaw)*Math.cos(pitch));
      }else controls.update();'''
rep(old_tick, new_tick)

rep(
    "    keys.current.clear();pad.current={forward:0,right:0};",
    "    keys.current.clear();pad.current={forward:0,right:0};drive.current={forward:0,turn:0};"
)

marker2 = "  // Model changes fit once; changing materials, overlay or wall height preserves the camera."
immersive_code = r'''  async function enterIndoor(room?:any){
    if(!model||error||!nav?.rooms.length||model.footprintSource!=='outline')return;
    preset('indoor',room);setShowPhotoDrawer(false);
    const mobileLike=window.matchMedia('(pointer: coarse)').matches||window.innerWidth<=900;
    if(!mobileLike)return;
    setImmersive(true);document.body.classList.add('fv-immersive-open');
    setPortrait(window.innerHeight>window.innerWidth);
    try{if(viewer.current?.requestFullscreen&&!document.fullscreenElement)await viewer.current.requestFullscreen();}catch{}
    try{const o=screen.orientation as any;if(o?.lock)await o.lock('landscape');}catch{}
  }
  async function exitIndoor(){
    drive.current={forward:0,turn:0};pad.current={forward:0,right:0};keys.current.clear();
    setImmersive(false);document.body.classList.remove('fv-immersive-open');
    try{const o=screen.orientation as any;o?.unlock?.();}catch{}
    try{if(document.fullscreenElement)await document.exitFullscreen();}catch{}
    preset('bird');
  }
  useEffect(()=>{
    if(!immersive)return;const update=()=>setPortrait(window.innerHeight>window.innerWidth);update();
    window.addEventListener('resize',update);window.addEventListener('orientationchange',update);
    return()=>{window.removeEventListener('resize',update);window.removeEventListener('orientationchange',update);};
  },[immersive]);
  useEffect(()=>()=>{document.body.classList.remove('fv-immersive-open');},[]);

'''
rep(marker2, immersive_code + marker2)

rep(
    "  return <section className=\"floorplan-viewer\" aria-label=\"3D 格局工作區\" data-camera-mode={mode}>",
    "  return <section ref={viewer} className={`floorplan-viewer ${immersive?'fv-immersive':''}`} aria-label=\"3D 格局工作區\" data-camera-mode={mode}>"
)
rep(
    "      {mode==='indoor'&&<div className=\"fv-walk\">",
    "      {mode==='indoor'&&!immersive&&<div className=\"fv-walk\">"
)

hint = "      {!loading&&!error&&model&&<div className=\"fv-hint\">{mode==='indoor'?'拖曳環顧 · W/A/S/D 或方向鈕行走':model.footprintSource==='estimated'?'請在 2D 校正外框，以啟用室內漫遊':'拖曳旋轉 · 滾輪縮放'}</div>}"
hud = r'''      {!loading&&!error&&model&&<div className="fv-hint">{mode==='indoor'?'拖曳環顧 · W/A/S/D 或方向鈕行走':model.footprintSource==='estimated'?'請在 2D 校正外框，以啟用室內漫遊':'拖曳旋轉 · 滾輪縮放'}</div>}
      {immersive&&mode==='indoor'&&<div className="fv-indoor-hud">
        <div className="fv-indoor-topbar">
          <button type="button" className="fv-exit" onClick={()=>void exitIndoor()}>✕ 離開漫遊</button>
          <label className="fv-indoor-room"><span>空間</span><select aria-label="切換室內空間" value={roomId} onChange={e=>preset('indoor',nav?.rooms.find((r:any)=>r.id===e.target.value))}>{nav?.rooms.map((r:any)=><option key={r.id} value={r.id}>{r.label}</option>)}</select></label>
          <button type="button" onClick={()=>preset('indoor',activeRoom||nav?.rooms[0])}>↺ 回定位</button>
        </div>
        <div className="fv-joysticks">
          <AxisJoystick axis="vertical" label="前進・後退" onValue={v=>{drive.current.forward=v;}}/>
          <AxisJoystick axis="horizontal" label="左轉・右轉" onValue={v=>{drive.current.turn=v;}}/>
        </div>
        {portrait&&<div className="fv-rotate-hint"><div className="fv-rotate-card"><span className="fv-rotate-icon">↻📱</span><strong>請將手機橫放</strong><p>已嘗試自動切換橫向；iPhone 主畫面 App 不允許網站強制旋轉時，將手機橫放即可開始雙搖桿漫遊。</p></div></div>}
      </div>}'''
rep(hint, hud)

rep(
    "                      preset('indoor', nav.rooms[selectedPhotoIdx]);",
    "                      void enterIndoor(nav.rooms[selectedPhotoIdx]);"
)

old_footer = "    <footer className=\"fv-footer\"><nav aria-label=\"模型視角\">{([{id:'bird',label:'立體鳥瞰'},{id:'top',label:'整體俯視'},{id:'iso',label:'等角視圖'},{id:'indoor',label:'進入室內'}] as const).map(p=><button key={p.id} aria-pressed={mode===p.id} disabled={!model||!!error||(p.id==='indoor'&&(!nav?.rooms.length||model.footprintSource!=='outline'))} onClick={()=>preset(p.id)}>{p.label}</button>)}</nav><label className=\"fv-height\">牆高 <input aria-label=\"牆高\" type=\"range\" min=\"2\" max=\"3.6\" step=\".1\" value={wallHeight} onChange={e=>setWallHeight(Number(e.target.value))}/><output>{wallHeight.toFixed(1)} m</output></label></footer>"
new_footer = "    <footer className=\"fv-footer\"><nav aria-label=\"模型視角\">{([{id:'bird',label:'立體鳥瞰'},{id:'top',label:'整體俯視'},{id:'iso',label:'等角視圖'},{id:'indoor',label:'🚪 進入室內'}] as const).map(p=><button key={p.id} className={p.id==='indoor'?'fv-enter-indoor':''} aria-pressed={mode===p.id} disabled={!model||!!error||(p.id==='indoor'&&(!nav?.rooms.length||model.footprintSource!=='outline'))} onClick={()=>p.id==='indoor'?void enterIndoor():preset(p.id)}>{p.label}</button>)}</nav><label className=\"fv-height\">牆高 <input aria-label=\"牆高\" type=\"range\" min=\"2\" max=\"3.6\" step=\".1\" value={wallHeight} onChange={e=>setWallHeight(Number(e.target.value))}/><output>{wallHeight.toFixed(1)} m</output></label></footer>"
rep(old_footer, new_footer)

p.write_text(s)
print('patched components/Floorplan3DViewer.tsx')
