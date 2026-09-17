from pathlib import Path

p = Path('components/Floorplan3DViewer.tsx')
s = p.read_text()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f'expected {count} match(es), got {n}: {old[:120]!r}')
    s = s.replace(old, new, count)

# 1) Joystick dead-zone + progressive response curve for precise small movements.
rep(
"    setOffset({x:dx,y:dy});const value=axis==='vertical'?-dy/radius:dx/radius;onValue(Math.max(-1,Math.min(1,value)));",
"    setOffset({x:dx,y:dy});const raw=Math.max(-1,Math.min(1,axis==='vertical'?-dy/radius:dx/radius));\n    const dead=.18,mag=Math.abs(raw);const value=mag<=dead?0:Math.sign(raw)*Math.pow((mag-dead)/(1-dead),1.65);\n    onValue(value);"
)

# 2) Reduce turn rate from ~109 deg/s to ~66 deg/s.
rep(
"        look.current.yaw+=turn*1.9*Math.min(.05,Math.max(0,dt));",
"        look.current.yaw+=turn*1.15*Math.min(.05,Math.max(0,dt));"
)

# 3) More natural walking pace and perspective in immersive mode.
rep(
"        const delta=walkingDelta(f,r,look.current.yaw,dt);",
"        const delta=walkingDelta(f,r,look.current.yaw,dt,1.05);"
)
rep(
"      e.camera.fov=76;e.camera.updateProjectionMatrix();",
"      e.camera.fov=68;e.camera.updateProjectionMatrix();"
)

# 4) Photo pins are useful in overview but visually huge at eye level.
rep(
"          pin.scale.set(0.65, 0.65, 0.65);",
"          const pinSize=mode==='indoor'?0.24:0.65;\n          pin.scale.set(pinSize, pinSize, pinSize);"
)

p.write_text(s)
print('patched Floorplan3DViewer.tsx')

css = Path('components/indoor-joystick.css')
c = css.read_text()

old = ".floorplan-viewer.fv-immersive .fv-caption{top:calc(10px + env(safe-area-inset-top));left:50%;right:auto;transform:translateX(-50%);align-items:center;background:rgba(15,23,42,.64);padding:5px 10px;border-radius:999px;backdrop-filter:blur(8px);white-space:nowrap}\n.floorplan-viewer.fv-immersive .fv-caption small{display:none}"
new = ".floorplan-viewer.fv-immersive .fv-caption{display:none!important}"
if c.count(old) != 1:
    raise SystemExit('immersive caption rule not found exactly once')
c = c.replace(old, new, 1)

old = ".fv-indoor-topbar{position:absolute;top:calc(10px + env(safe-area-inset-top));left:calc(10px + env(safe-area-inset-left));right:calc(10px + env(safe-area-inset-right));display:flex;align-items:center;justify-content:space-between;gap:8px;pointer-events:none}"
new = ".fv-indoor-topbar{position:absolute;top:calc(10px + env(safe-area-inset-top));left:calc(10px + env(safe-area-inset-left));right:calc(10px + env(safe-area-inset-right));display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;pointer-events:none}\n.fv-indoor-topbar>.fv-exit{justify-self:start}.fv-indoor-topbar>.fv-indoor-room{justify-self:center}.fv-indoor-topbar>button:last-child{justify-self:end}"
if c.count(old) != 1:
    raise SystemExit('indoor topbar rule not found exactly once')
c = c.replace(old, new, 1)

# Slightly smaller joysticks to free visual space while preserving large touch targets.
c = c.replace(".fv-stick-wrap{width:132px;", ".fv-stick-wrap{width:124px;", 1)
c = c.replace(".fv-stick-base{position:relative;width:116px;height:116px;", ".fv-stick-base{position:relative;width:108px;height:108px;", 1)

css.write_text(c)
print('patched indoor-joystick.css')
