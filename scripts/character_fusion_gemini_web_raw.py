#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets

CDP_HTTP = "http://127.0.0.1:9222"
LOCK_PATH = Path("/home/ubuntu/agent-data/runtime/locks/oracle-gui-profile.lock")

COMPOSER_SELECTORS = [
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]

RESPONSE_SELECTORS = [
    'model-response',
    '[data-test-id*="model-response"]',
    '.model-response-text',
    'message-content',
]

IMAGE_SELECTORS = [
    'model-response img',
    '[data-test-id*="model-response"] img',
    '.model-response-text img',
    'message-content img',
    'img[alt*="generated" i]',
]


class CDPClient:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.seq = 0

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.seq += 1
        call_id = self.seq
        await self.ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") != call_id:
                continue
            if msg.get("error"):
                raise RuntimeError(f"cdp_error:{method}:{msg['error']}")
            return dict(msg.get("result") or {})

    async def eval(self, expression: str) -> Any:
        result = await self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        remote = dict(result.get("result") or {})
        if remote.get("subtype") == "error":
            raise RuntimeError("cdp_eval_error")
        return remote.get("value")


def target_ws() -> str:
    with urllib.request.urlopen(CDP_HTTP + "/json/list", timeout=5) as response:
        rows = json.loads(response.read().decode("utf-8"))
    for row in rows:
        if row.get("type") == "page" and "gemini.google.com" in str(row.get("url") or ""):
            ws = str(row.get("webSocketDebuggerUrl") or "")
            if ws:
                return ws
    raise RuntimeError("gemini_web_no_session")


def js_first_visible(selectors: list[str]) -> str:
    return """(() => {
      const sels=%s;
      for (const s of sels) {
        for (const el of document.querySelectorAll(s)) {
          const r=el.getBoundingClientRect();
          const st=getComputedStyle(el);
          if ((r.width||r.height) && st.visibility!=='hidden' && st.display!=='none') return s;
        }
      }
      return '';
    })()""" % json.dumps(selectors)


def js_response_rows() -> str:
    return """(() => {
      const sels=%s, out=[], seen=new Set();
      for (const s of sels) {
        const rows=[...document.querySelectorAll(s)].slice(-10);
        for (const el of rows) {
          const t=String(el.innerText||el.textContent||'').trim();
          if (t && !seen.has(t)) { seen.add(t); out.push(t); }
        }
      }
      return out;
    })()""" % json.dumps(RESPONSE_SELECTORS)


def js_images() -> str:
    return """(() => {
      const sels=%s, out=[], seen=new Set();
      for (const s of sels) {
        for (const el of document.querySelectorAll(s)) {
          const r=el.getBoundingClientRect(), st=getComputedStyle(el);
          if (!(r.width||r.height) || st.visibility==='hidden' || st.display==='none') continue;
          if (r.width < 180 || r.height < 180) continue;
          const src=String(el.currentSrc||el.src||'');
          const key=src+'|'+Math.round(r.width)+'x'+Math.round(r.height);
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({
            key, src,
            x:r.left+window.scrollX,
            y:r.top+window.scrollY,
            width:r.width,
            height:r.height
          });
        }
      }
      return out;
    })()""" % json.dumps(IMAGE_SELECTORS)


async def ensure_composer(client: CDPClient) -> str:
    selector = str(await client.eval(js_first_visible(COMPOSER_SELECTORS)) or "")
    if not selector:
        raise RuntimeError("gemini_web_composer_not_found")
    return selector


async def upload_image(client: CDPClient, image_path: Path) -> None:
    doc = await client.call("DOM.getDocument", {"depth": 1})
    root_id = int((doc.get("root") or {}).get("nodeId") or 0)
    if not root_id:
        raise RuntimeError("gemini_web_dom_root_missing")

    found = await client.call("DOM.querySelector", {"nodeId": root_id, "selector": 'input[type="file"]'})
    node_id = int(found.get("nodeId") or 0)

    if not node_id:
        clicked = await client.eval("""(() => {
          const sels=[
            'button[aria-label*="upload" i]',
            'button[aria-label*="file" i]',
            'button[aria-label*="add" i]',
            '[data-test-id*="upload"]',
            '[data-test-id*="file"]'
          ];
          for(const s of sels){
            for(const el of document.querySelectorAll(s)){
              const r=el.getBoundingClientRect(),st=getComputedStyle(el);
              if((r.width||r.height)&&st.visibility!=='hidden'&&st.display!=='none'){
                el.click(); return true;
              }
            }
          }
          return false;
        })()""")
        if clicked:
            await asyncio.sleep(1.0)
            doc = await client.call("DOM.getDocument", {"depth": 1})
            root_id = int((doc.get("root") or {}).get("nodeId") or 0)
            found = await client.call("DOM.querySelector", {"nodeId": root_id, "selector": 'input[type="file"]'})
            node_id = int(found.get("nodeId") or 0)

    if not node_id:
        raise RuntimeError("gemini_web_image_upload_control_not_found")

    await client.call("DOM.setFileInputFiles", {
        "nodeId": node_id,
        "files": [str(image_path.resolve())],
    })
    await asyncio.sleep(2.0)


async def fill_and_submit(client: CDPClient, selector: str, prompt: str) -> None:
    expression = """(() => {
      const s=%s, value=%s;
      const els=[...document.querySelectorAll(s)];
      const el=els.find(x=>{
        const r=x.getBoundingClientRect(),st=getComputedStyle(x);
        return (r.width||r.height)&&st.visibility!=='hidden'&&st.display!=='none';
      });
      if(!el) return false;
      el.focus();
      if('value' in el){
        const proto=Object.getPrototypeOf(el);
        const desc=Object.getOwnPropertyDescriptor(proto,'value');
        if(desc&&desc.set) desc.set.call(el,value); else el.value=value;
      } else {
        el.textContent=value;
      }
      el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));
      el.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()""" % (json.dumps(selector), json.dumps(prompt))
    if not await client.eval(expression):
        raise RuntimeError("gemini_web_composer_fill_failed")
    await asyncio.sleep(0.3)
    await client.call("Input.dispatchKeyEvent", {
        "type": "rawKeyDown",
        "key": "Enter",
        "code": "Enter",
        "windowsVirtualKeyCode": 13,
        "nativeVirtualKeyCode": 13,
    })
    await client.call("Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": "Enter",
        "code": "Enter",
        "windowsVirtualKeyCode": 13,
        "nativeVirtualKeyCode": 13,
    })


async def run_vlm(prompt: str, image_path: Path, output: Path) -> None:
    ws_url = target_ws()
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=2, max_size=8 * 1024 * 1024) as ws:
        client = CDPClient(ws)
        selector = await ensure_composer(client)
        baseline = list(await client.eval(js_response_rows()) or [])
        await upload_image(client, image_path)
        await fill_and_submit(client, selector, prompt)

        deadline = time.monotonic() + 150
        last = ""
        stable = 0
        while time.monotonic() < deadline:
            rows = list(await client.eval(js_response_rows()) or [])
            fresh = [str(x) for x in rows if str(x) not in baseline and str(x).strip()]
            if fresh:
                current = fresh[-1].strip()
                if current == last:
                    stable += 1
                else:
                    last = current
                    stable = 0
                if ("{" in current and "}" in current and stable >= 1) or stable >= 2:
                    output.write_text(current, encoding="utf-8")
                    return
            await asyncio.sleep(1.5)
        raise TimeoutError("gemini_web_vlm_response_timeout")


async def run_render(prompt: str, output: Path) -> None:
    ws_url = target_ws()
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=2, max_size=8 * 1024 * 1024) as ws:
        client = CDPClient(ws)
        selector = await ensure_composer(client)
        baseline = {str(x.get("key") or "") for x in (await client.eval(js_images()) or [])}
        await fill_and_submit(client, selector, prompt)

        deadline = time.monotonic() + 180
        candidate = None
        while time.monotonic() < deadline:
            rows = list(await client.eval(js_images()) or [])
            fresh = [x for x in rows if str(x.get("key") or "") not in baseline]
            if fresh:
                candidate = fresh[-1]
                break
            await asyncio.sleep(1.5)

        if not candidate:
            raise TimeoutError("gemini_web_image_response_timeout")

        shot = await client.call("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {
                "x": max(0, float(candidate["x"])),
                "y": max(0, float(candidate["y"])),
                "width": float(candidate["width"]),
                "height": float(candidate["height"]),
                "scale": 1,
            },
        })
        data = base64.b64decode(str(shot.get("data") or ""))
        if len(data) < 10000:
            raise RuntimeError("gemini_web_image_capture_invalid")
        output.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    vlm = sub.add_parser("vlm")
    vlm.add_argument("--prompt", required=True)
    vlm.add_argument("--image", required=True)
    vlm.add_argument("--output", required=True)

    render = sub.add_parser("render")
    render.add_argument("--prompt", required=True)
    render.add_argument("--output", required=True)

    args = parser.parse_args()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if args.command == "vlm":
            asyncio.run(run_vlm(
                Path(args.prompt).read_text(encoding="utf-8"),
                Path(args.image),
                Path(args.output),
            ))
            print("character_fusion_gemini_web_vlm_raw_cdp=PASS")
        else:
            asyncio.run(run_render(
                Path(args.prompt).read_text(encoding="utf-8"),
                Path(args.output),
            ))
            print("character_fusion_gemini_web_render_raw_cdp=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
