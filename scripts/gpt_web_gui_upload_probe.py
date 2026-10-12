#!/usr/bin/env python3
"""Bounded UI file-chooser comparison for GPT Web. No prompt is sent."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from gpt_web_response_bridge import _page, _focus_composer, _submission_snapshot

def run(cdp_url: str, image: Path) -> dict:
    if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("invalid_fixture")
    page = _page(cdp_url)
    try:
        _focus_composer(page)
        before = _submission_snapshot(page, "gui-probe-no-send")
        # Capture chooser events through an opt-in temporary CDP listener.
        page.connection.file_chooser_events = []
        page.call("Page.enable")
        page.call("Page.setInterceptFileChooserDialog", {"enabled": True})
        try:
            candidate = page.evaluate("""(() => {
              const labels = ['attach','add files','upload','附件','上傳','新增'];
              const nodes = Array.from(document.querySelectorAll('button,[role="button"]'));
              for (const el of nodes) {
                const caption = ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('data-testid') || '')).toLowerCase();
                if (!labels.some(x => caption.includes(x))) continue;
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) return {x:r.left+r.width/2,y:r.top+r.height/2};
              }
              return null;
            })()""")
            if not isinstance(candidate, dict):
                return {"status": "ATTACH_BUTTON_NOT_FOUND", "before": before.get("attachmentSummary", {})}
            x, y = float(candidate["x"]), float(candidate["y"])
            for kind in ("mousePressed", "mouseReleased"):
                page.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})
            deadline=time.monotonic()+4
            while time.monotonic()<deadline and not page.connection.file_chooser_events:
                page.evaluate("1")
                time.sleep(0.2)
            events=page.connection.file_chooser_events
            if not events:
                return {"status": "FILE_CHOOSER_NOT_OPENED", "before":before.get("attachmentSummary",{})}
            chooser=events[-1]
            backend_id=chooser.get("backendNodeId")
            if not isinstance(backend_id,int):
                return {"status":"CHOOSER_NO_BACKEND_NODE"}
            page.call("DOM.setFileInputFiles", {"backendNodeId":backend_id,"files":[str(image)]})
            deadline=time.monotonic()+8
            after={}
            while time.monotonic()<deadline:
                after=_submission_snapshot(page,"gui-probe-no-send").get("attachmentSummary",{})
                if int(after.get("imagePreviewCount") or 0)>0:
                    break
                time.sleep(0.4)
            return {"status":"PREVIEW_OBSERVED" if int(after.get("imagePreviewCount") or 0)>0 else "PREVIEW_UNVERIFIED",
                    "before":before.get("attachmentSummary",{}),"after":after}
        finally:
            page.call("Page.setInterceptFileChooserDialog", {"enabled":False})
    finally:
        page.close()

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
    p.add_argument("--image",type=Path,required=True)
    args=p.parse_args()
    result=run(args.cdp_url,args.image.resolve())
    print("gpt_web_native_chooser_probe="+json.dumps(result,ensure_ascii=False,sort_keys=True))
    # Diagnostic-only, no message is sent and nothing can pass acceptance.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
