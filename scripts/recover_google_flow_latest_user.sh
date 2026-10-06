#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "google_flow_recover=WRONG_USER"
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
OUT_ROOT="/home/ubuntu/agent-data/artifacts/google-flow-recovery"
test -x "$PY"
mkdir -p "$OUT_ROOT"

"$PY" - "$OUT_ROOT" <<'PY'
from __future__ import annotations
import hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

out_root=Path(sys.argv[1])
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_dir=out_root/stamp
run_dir.mkdir(parents=True,exist_ok=True)

print("google_flow_recover_stage=CONNECT_CDP",flush=True)
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=10000)
    ctx=browser.contexts[0]
    page=next((x for x in ctx.pages if "flow.google.com" in str(x.url or "")),None)
    if page is None:
        page=ctx.new_page()
        page.goto("https://flow.google.com/",wait_until="domcontentloaded",timeout=60000)
        page.wait_for_timeout(5000)
    print("google_flow_recover_stage=FLOW_LOADED",flush=True)
    vids=page.locator("video")
    video=None
    for i in range(min(vids.count(),20)):
        item=vids.nth(i)
        try:
            if item.is_visible(timeout=300):
                video=item
                break
        except Exception:
            pass
    if video is None:
        print("google_flow_recover=NO_VISIBLE_VIDEO")
        raise SystemExit(0)
    print("google_flow_recover_stage=VIDEO_VISIBLE",flush=True)
    src=str(video.get_attribute("src") or "")
    try:
        current_src=str(video.evaluate("(el) => el.currentSrc || el.src || ''") or "")
    except Exception:
        current_src=""
    try:
        source_src=str(video.locator("source").first.get_attribute("src") or "")
    except Exception:
        source_src=""
    candidates=[]
    for value in (current_src,src,source_src):
        if value and value not in candidates:
            candidates.append(value)
    print("google_flow_recover_video_scheme="+(("blob" if any(x.startswith("blob:") for x in candidates) else "http") if candidates else "none"))

    output=run_dir/"google-flow-recovered.mp4"
    downloaded=False

    # First try provider-backed HTTP(S) media URLs.
    for media_url in candidates:
        if not media_url.startswith(("http://","https://")):
            continue
        try:
            resp=ctx.request.get(media_url,timeout=120000)
            if resp.ok and len(resp.body()) >= 10000:
                output.write_bytes(resp.body())
                downloaded=True
                break
        except Exception:
            pass

    # If Flow exposes a blob: URL, ask Chromium itself to download that exact
    # already-generated media. This is read-only and does not trigger generation.
    if not downloaded:
        blob_url=next((x for x in candidates if x.startswith("blob:")),None)
        if blob_url:
            try:
                with page.expect_download(timeout=20000) as dl:
                    page.evaluate("""(u) => {
                      const a=document.createElement('a');
                      a.href=u; a.download='google-flow-recovered.mp4';
                      document.body.appendChild(a); a.click(); a.remove();
                    }""",blob_url)
                dl.value.save_as(str(output))
                downloaded=True
            except Exception:
                pass

    # Try visible download controls, including localized labels.
    if not downloaded:
        for pattern in ("Download","下載","Save","儲存"):
            try:
                loc=page.get_by_role("button",name=pattern,exact=False)
                if loc.count():
                    with page.expect_download(timeout=15000) as dl:
                        loc.first.click(timeout=3000)
                    dl.value.save_as(str(output))
                    downloaded=True
                    break
            except Exception:
                pass

    # Some Flow surfaces hide Download behind a more/options menu.
    if not downloaded:
        for pattern in ("More options","More","更多選項","更多"):
            try:
                loc=page.get_by_role("button",name=pattern,exact=False)
                if not loc.count():
                    continue
                loc.first.click(timeout=3000)
                page.wait_for_timeout(500)
                for dl_name in ("Download","下載","Save","儲存"):
                    dl_loc=page.get_by_role("menuitem",name=dl_name,exact=False)
                    if not dl_loc.count():
                        dl_loc=page.get_by_text(dl_name,exact=False)
                    if dl_loc.count():
                        with page.expect_download(timeout=15000) as dl:
                            dl_loc.first.click(timeout=3000)
                        dl.value.save_as(str(output))
                        downloaded=True
                        break
                if downloaded:
                    break
            except Exception:
                pass

    if not downloaded or not output.exists() or output.stat().st_size < 10000:
        controls=[]
        try:
            for sel in ("button","a"):
                loc=page.locator(sel)
                for i in range(min(loc.count(),30)):
                    item=loc.nth(i)
                    try:
                        if not item.is_visible(timeout=100):
                            continue
                        label=(item.get_attribute("aria-label") or item.inner_text(timeout=300) or "").strip()
                        if label:
                            controls.append((sel+":"+label)[:120])
                    except Exception:
                        pass
        except Exception:
            pass
        if controls:
            print("google_flow_recover_controls="+json.dumps(controls[:40],ensure_ascii=False,separators=(",",":")))
        print("google_flow_recover=VIDEO_VISIBLE_NOT_DOWNLOADED")
        raise SystemExit(0)
    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    print("google_flow_recover=PASS")
    print("google_flow_recover_output="+str(output))
    print("google_flow_recover_bytes="+str(len(raw)))
    print("google_flow_recover_sha256="+sha)
PY
