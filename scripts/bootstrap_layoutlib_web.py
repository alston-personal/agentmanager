#!/usr/bin/env python3
"""Add a zero-dependency web demo/API shell to a bootstrapped LayoutLib tree.

The web layer deliberately depends only on LayoutLib's public API.  It exposes a
small JSON/base64 HTTP contract that is easy to reverse-proxy into an existing
website and keeps parsing/reconstruction behind the Spatial IR boundary.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import textwrap

FILES = {
    "web_demo/server.py": r'''
from __future__ import annotations

import argparse
import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile

from layoutlib import parse_floorplan

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "static" / "index.html"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _json_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _parse_payload(payload: dict) -> dict:
    filename = Path(str(payload.get("filename") or "upload.pgm")).name
    if not filename:
        raise ValueError("filename is required")
    raw_b64 = payload.get("content_base64")
    if not isinstance(raw_b64, str) or not raw_b64:
        raise ValueError("content_base64 is required")
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except Exception as exc:
        raise ValueError("content_base64 is invalid") from exc
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("upload exceeds 12 MiB")
    scale = float(payload.get("meters_per_pixel", 0.02))
    threshold = int(payload.get("threshold", 128))
    min_len = int(payload.get("min_wall_length_px", 16))
    with tempfile.TemporaryDirectory(prefix="layoutlib-web-") as td:
        src = Path(td) / filename
        src.write_bytes(raw)
        ir = parse_floorplan(
            src,
            meters_per_pixel=scale,
            threshold=threshold,
            min_wall_length_px=min_len,
        )
    return ir.to_dict()


class Handler(BaseHTTPRequestHandler):
    server_version = "LayoutLibWeb/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, _json_bytes({"ok": True, "service": "layoutlib-web", "version": "0.1"}), "application/json; charset=utf-8")
            return
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/parse":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_UPLOAD_BYTES * 2:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            ir = _parse_payload(payload)
            self._send(200, _json_bytes({"ok": True, "ir": ir, "wall_count": len(ir["walls"])}), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(400, _json_bytes({"ok": False, "error": str(exc)}), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        if os.environ.get("LAYOUTLIB_WEB_QUIET") != "1":
            super().log_message(fmt, *args)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="LayoutLib embeddable web demo")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"LayoutLib web demo listening on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    "web_demo/static/index.html": r'''
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LayoutLib Demo</title>
<style>
:root{color-scheme:dark;background:#0b1020;color:#eef2ff;font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif}
*{box-sizing:border-box} body{margin:0;background:linear-gradient(145deg,#0b1020,#131a31);min-height:100vh}
main{max-width:1180px;margin:auto;padding:32px 20px 56px} h1{margin:0 0 8px;font-size:clamp(28px,5vw,54px)}
.lead{color:#aab5d6;margin:0 0 26px}.panel{background:#11182c;border:1px solid #283454;border-radius:16px;padding:18px;box-shadow:0 14px 50px #0005}
.controls{display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:12px;align-items:end}.controls label{font-size:13px;color:#aab5d6;display:grid;gap:6px}
input,button{min-height:42px;border-radius:10px;border:1px solid #344260;background:#0b1122;color:#eef2ff;padding:8px 10px} button{cursor:pointer;background:#263d80;font-weight:700;padding-inline:18px}button:disabled{opacity:.45;cursor:wait}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.stage{min-height:420px;position:relative;overflow:hidden;background:#070b15;border:1px solid #283454;border-radius:14px}
.stage h2{position:absolute;z-index:3;top:10px;left:14px;margin:0;font-size:13px;color:#aab5d6;font-weight:600}canvas,svg{width:100%;height:100%;display:block;position:absolute;inset:0;padding-top:34px}
#source{object-fit:contain}#ir{white-space:pre-wrap;max-height:260px;overflow:auto;font:12px/1.45 ui-monospace,monospace;background:#080d19;border-radius:12px;padding:14px;color:#c9d4ff;margin:16px 0 0}
#status{margin-top:12px;min-height:24px;color:#9fb1e8}.ok{color:#8ee6b0!important}.bad{color:#ff9b9b!important}.hint{font-size:12px;color:#7f8db5;margin-top:8px}
@media(max-width:780px){.controls,.grid{grid-template-columns:1fr}.stage{min-height:330px}}
</style>
</head>
<body><main>
<h1>LayoutLib</h1><p class="lead">Floor plan → Spatial IR → browser preview. Core parser and Web UI are decoupled by the versioned IR contract.</p>
<section class="panel">
<div class="controls">
<label>平面圖<input id="file" type="file" accept="image/png,image/jpeg,image/bmp,.pgm"></label>
<label>meters / pixel<input id="scale" type="number" min="0.0001" step="0.001" value="0.02"></label>
<label>最短牆線(px)<input id="minlen" type="number" min="2" step="1" value="16"></label>
<button id="run">解析</button>
</div><div id="status">選擇圖檔後按「解析」。</div><div class="hint">v0.1 demo：高對比、主要水平/垂直牆線；比例需明確提供。</div>
<div class="grid">
<div class="stage"><h2>原圖 + 牆線 overlay</h2><img id="source" alt="source"><svg id="overlay" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet"></svg></div>
<div class="stage"><h2>3D preview（瀏覽器即時投影）</h2><canvas id="three"></canvas></div>
</div><pre id="ir">Spatial IR will appear here.</pre>
</section></main>
<script>
const $=id=>document.getElementById(id), file=$('file'), run=$('run'), status=$('status'), source=$('source'), overlay=$('overlay'), canvas=$('three'), irbox=$('ir');
let latest=null;
function base64(f){return new Promise((ok,bad)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]);r.onerror=bad;r.readAsDataURL(f)})}
function show2d(ir){const w=ir.image_width_px,h=ir.image_height_px,s=ir.meters_per_pixel;overlay.setAttribute('viewBox',`0 0 ${w} ${h}`);overlay.innerHTML='';for(const wall of ir.walls){const el=document.createElementNS('http://www.w3.org/2000/svg','line');el.setAttribute('x1',wall.start.x/s);el.setAttribute('y1',wall.start.y/s);el.setAttribute('x2',wall.end.x/s);el.setAttribute('y2',wall.end.y/s);el.setAttribute('stroke','#42f5b3');el.setAttribute('stroke-width',Math.max(2,wall.thickness/s));el.setAttribute('stroke-opacity','.65');overlay.appendChild(el)}}
function show3d(ir){const dpr=devicePixelRatio||1,rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,rect.width*dpr);canvas.height=Math.max(1,rect.height*dpr);const c=canvas.getContext('2d');c.scale(dpr,dpr);c.clearRect(0,0,rect.width,rect.height);if(!ir.walls.length)return;const pts=ir.walls.flatMap(w=>[w.start,w.end]),xs=pts.map(p=>p.x),ys=pts.map(p=>p.y),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys),span=Math.max(maxx-minx,maxy-miny,1),k=Math.min(rect.width,rect.height)*.58/span,ox=rect.width*.5,oy=rect.height*.62;
const project=(x,y,z)=>[ox+(x-minx-(maxx-minx)/2)*k-(y-miny-(maxy-miny)/2)*k*.45,oy+(y-miny-(maxy-miny)/2)*k*.30-z*k*.22];c.lineWidth=2;c.strokeStyle='#83a7ff';for(const w of ir.walls){const a=project(w.start.x,w.start.y,0),b=project(w.end.x,w.end.y,0),c1=project(w.end.x,w.end.y,w.height),d=project(w.start.x,w.start.y,w.height);c.beginPath();c.moveTo(...a);c.lineTo(...b);c.lineTo(...c1);c.lineTo(...d);c.closePath();c.stroke()}}
run.onclick=async()=>{if(!file.files[0]){status.textContent='請先選擇圖檔。';status.className='bad';return}run.disabled=true;status.textContent='解析中…';status.className='';try{const f=file.files[0];source.src=URL.createObjectURL(f);const body={filename:f.name,content_base64:await base64(f),meters_per_pixel:Number($('scale').value),min_wall_length_px:Number($('minlen').value)};const r=await fetch('/api/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await r.json();if(!data.ok)throw new Error(data.error||'parse failed');latest=data.ir;show2d(latest);show3d(latest);irbox.textContent=JSON.stringify(latest,null,2);status.textContent=`完成：辨識 ${data.wall_count} 面牆`;status.className='ok'}catch(e){status.textContent='失敗：'+e.message;status.className='bad'}finally{run.disabled=false}};
addEventListener('resize',()=>latest&&show3d(latest));
</script></body></html>
''',
    "docs/WEB_DEMO.md": r'''
# LayoutLib Web Demo / Integration

The web demo is an adapter over LayoutLib's public API. It does not duplicate wall
recognition logic and does not make the web layer part of Spatial IR.

## Run

```bash
PYTHONPATH=src python3 web_demo/server.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`.

## HTTP contract

`GET /api/health` returns service/version status.

`POST /api/parse` accepts JSON:

```json
{
  "filename": "plan.pgm",
  "content_base64": "...",
  "meters_per_pixel": 0.02,
  "threshold": 128,
  "min_wall_length_px": 16
}
```

The response contains `ir` (Spatial IR 0.1) plus `wall_count`. The upload is kept
in a temporary directory and deleted immediately after parsing. Maximum decoded
upload size is 12 MiB.

For PNG/JPEG/BMP input, install Pillow (`pip install 'layoutlib[images]'`). P2 PGM
works with the standard-library-only core.

## Website integration

Reverse proxy a website path such as `/layoutlib/` to this service. Keep the
public site responsible for authentication/rate limiting/TLS and keep LayoutLib
responsible for parsing only. This separation also allows Telegram/LINE/agents to
reuse the same API without coupling them to the browser UI.

The current demo intentionally does not claim general architectural drawing
support. It visualizes the exact walls returned by the v0.1 deterministic parser.
''',
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    args = p.parse_args()
    root = Path(args.target).resolve()
    if not (root / "src" / "layoutlib").exists():
        raise SystemExit("target is not a bootstrapped LayoutLib tree")
    for rel, body in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    print(f"layoutlib_web_bootstrap=ok target={root} files={len(FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
