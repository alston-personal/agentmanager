from pathlib import Path

p = Path('components/Floorplan3DViewer.tsx')
s = p.read_text()

# Replace the one-axis joystick with a true two-axis analog stick.
start = s.index('function AxisJoystick(')
end = s.index('\n\nexport default function Floorplan3DViewer', start)
new_stick = r'''function DualJoystick({label,onValue}:{label:string;onValue:(value:{x:number;y:number})=>void}) {
  const base=useRef<HTMLDivElement>(null),active=useRef(false),[offset,setOffset]=useState({x:0,y:0});
  const reset=()=>{active.current=false;setOffset({x:0,y:0});onValue({x:0,y:0});};
  const apply=(e:React.PointerEvent<HTMLDivElement>)=>{
    const el=base.current;if(!el)return;
    const r=el.getBoundingClientRect(),radius=Math.max(24,Math.min(r.width,r.height)*.34);
    let dx=e.clientX-(r.left+r.width/2),dy=e.clientY-(r.top+r.height/2);
    const len=Math.hypot(dx,dy);if(len>radius){dx=dx/len*radius;dy=dy/len*radius;}
    setOffset({x:dx,y:dy});
    const rawX=dx/radius,rawY=-dy/radius,rawMag=Math.min(1,Math.hypot(rawX,rawY));
    const dead=.14,eased=rawMag<=dead?0:Math.pow((rawMag-dead)/(1-dead),1.45),scale=rawMag>0?eased/rawMag:0;
    onValue({x:rawX*scale,y:rawY*scale});
  };
  return <div className="fv-stick-wrap" aria-label={label}>
    <div ref={base} className={`fv-stick-base ${active.current?'is-active':''}`}
      onPointerDown={e=>{e.preventDefault();e.stopPropagation();active.current=true;e.currentTarget.setPointerCapture(e.pointerId);apply(e);}}
      onPointerMove={e=>{if(active.current){e.preventDefault();e.stopPropagation();apply(e);}}}
      onPointerUp={e=>{try{e.currentTarget.releasePointerCapture(e.pointerId);}catch{}reset();}}
      onPointerCancel={reset} onLostPointerCapture={reset}>
      <div className="fv-stick-knob" style={{'--stick-x':`${offset.x}px`,'--stick-y':`${offset.y}px`} as React.CSSProperties}/>
    </div>
    <span className="fv-stick-label">{label}</span>
  </div>;
}'''
s = s[:start] + new_stick + s[end:]

old = "const keys=useRef(new Set<string>()),pad=useRef({forward:0,right:0}),drive=useRef({forward:0,turn:0}),look=useRef({yaw:0,pitch:0});"
new = "const keys=useRef(new Set<string>()),pad=useRef({forward:0,right:0}),drive=useRef({forward:0,right:0,lookX:0,lookY:0}),look=useRef({yaw:0,pitch:0});"
if old not in s:
    raise SystemExit('drive state anchor not found')
s = s.replace(old, new, 1)

# Reset every analog channel whenever focus/mode changes.
s = s.replace('drive.current={forward:0,turn:0}', 'drive.current={forward:0,right:0,lookX:0,lookY:0}')

old_tick = r'''        const keyboardF=Number(keys.current.has('KeyW')||keys.current.has('ArrowUp'))-Number(keys.current.has('KeyS')||keys.current.has('ArrowDown'));
        const keyboardR=Number(keys.current.has('KeyD'))-Number(keys.current.has('KeyA'));
        const keyTurn=Number(keys.current.has('ArrowRight'))-Number(keys.current.has('ArrowLeft'));
        const turn=Math.max(-1,Math.min(1,drive.current.turn+keyTurn));
        look.current.yaw+=turn*1.15*Math.min(.05,Math.max(0,dt));
        const f=Math.max(-1,Math.min(1,keyboardF+pad.current.forward+drive.current.forward));
        const r=Math.max(-1,Math.min(1,keyboardR+pad.current.right));
        const delta=walkingDelta(f,r,look.current.yaw,dt,1.05);'''
new_tick = r'''        const keyboardF=Number(keys.current.has('KeyW')||keys.current.has('ArrowUp'))-Number(keys.current.has('KeyS')||keys.current.has('ArrowDown'));
        const keyboardR=Number(keys.current.has('KeyD'))-Number(keys.current.has('KeyA'));
        const keyTurn=Number(keys.current.has('ArrowRight'))-Number(keys.current.has('ArrowLeft'));
        const lookX=Math.max(-1,Math.min(1,drive.current.lookX+keyTurn));
        look.current.yaw+=lookX*1.15*Math.min(.05,Math.max(0,dt));
        look.current.pitch=Math.max(-1.15,Math.min(1.15,look.current.pitch+drive.current.lookY*.95*Math.min(.05,Math.max(0,dt))));
        const f=Math.max(-1,Math.min(1,keyboardF+pad.current.forward+drive.current.forward));
        const r=Math.max(-1,Math.min(1,keyboardR+pad.current.right+drive.current.right));
        const delta=walkingDelta(f,r,look.current.yaw,dt,1.05);'''
if old_tick not in s:
    raise SystemExit('animation tick anchor not found')
s = s.replace(old_tick, new_tick, 1)

old_hud = r'''          <AxisJoystick axis="vertical" label="前進・後退" onValue={v=>{drive.current.forward=v;}}/>
          <AxisJoystick axis="horizontal" label="左轉・右轉" onValue={v=>{drive.current.turn=v;}}/>'''
new_hud = r'''          <DualJoystick label="移動 · 前後左右" onValue={v=>{drive.current.forward=v.y;drive.current.right=v.x;}}/>
          <DualJoystick label="視角 · 上下左右" onValue={v=>{drive.current.lookX=v.x;drive.current.lookY=v.y;}}/>'''
if old_hud not in s:
    raise SystemExit('HUD joystick anchor not found')
s = s.replace(old_hud, new_hud, 1)

# Keep one door icon only: mobile CSS already supplies the decorative door.
s = s.replace("{id:'indoor',label:'🚪 進入室內'}", "{id:'indoor',label:'進入室內'}")

if 'AxisJoystick' in s or 'drive.current.turn' in s:
    raise SystemExit('stale one-axis joystick references remain')

p.write_text(s)
print('patched dual-stick movement/look controls')
