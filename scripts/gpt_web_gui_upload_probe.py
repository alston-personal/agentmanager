#!/usr/bin/env python3
"""Bounded UI file-chooser comparison for GPT Web. No prompt is sent."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from gpt_web_response_bridge import CdpPage, _browser_ws_url, _create_target, _open_target_connection, _focus_composer, _submission_snapshot

def run(cdp_url: str, image: Path) -> dict:
    if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("invalid_fixture")
    target = _create_target(cdp_url, 'https://chatgpt.com/')
    page = _open_target_connection(cdp_url, target)
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
                # ChatGPT may open an attachment menu first. Restrict the next
                # click to a visible menu option explicitly labelled for files.
                option = page.evaluate("""(() => {
                  const nodes = Array.from(document.querySelectorAll(
                    '[role="menuitem"],[role="option"],[data-radix-menu-content] button,[role="menu"] button'
                  ));
                  for (const el of nodes) {
                    const title = ((el.getAttribute('aria-label') || '') + ' ' +
                      (el.textContent || '')).trim().toLowerCase();
                    const allowed = ['upload file','upload from computer','add photos','上傳檔案','從電腦上傳','照片與檔案'];
                    if (!allowed.some(x => title.includes(x))) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return {x:r.left+r.width/2,y:r.top+r.height/2};
                  }
                  return null;
                })()""")
                if not isinstance(option, dict):
                    menu_state = page.evaluate("""(() => {
                      const selectors = ['[role="menu"]','[role="menuitem"]','[role="dialog"]',
                        '[role="option"]','[data-state="open"]','[aria-expanded="true"]'];
                      const counts = {};
                      for (const selector of selectors) {
                        counts[selector] = Array.from(document.querySelectorAll(selector))
                          .filter(el => el.getBoundingClientRect().width > 0).length;
                      }
                      return counts;
                    })()""")
                    return {"status":"ATTACH_MENU_UPLOAD_ITEM_NOT_FOUND",
                      "menuStructure":menu_state,"before":before.get("attachmentSummary",{})}
                for kind in ("mousePressed", "mouseReleased"):
                    page.call("Input.dispatchMouseEvent", {"type":kind,
                      "x":float(option["x"]),"y":float(option["y"]),
                      "button":"left","clickCount":1})
                deadline=time.monotonic()+4
                while time.monotonic()<deadline and not page.connection.file_chooser_events:
                    page.evaluate("1")
                    time.sleep(0.2)
                events=page.connection.file_chooser_events
                if not events:
                    return {"status":"FILE_CHOOSER_NOT_OPENED_AFTER_MENU","before":before.get("attachmentSummary",{})}
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
        # The unsent test attachment must never survive into another invoke.
        browser = CdpPage(_browser_ws_url(cdp_url))
        try:
            browser.call('Target.closeTarget', {'targetId': target['id']})
        finally:
            browser.close()

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
