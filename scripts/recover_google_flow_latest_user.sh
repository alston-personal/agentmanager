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
    output=run_dir/"google-flow-recovered.mp4"
    downloaded=False
    if src.startswith(("http://","https://")):
        try:
            resp=ctx.request.get(src,timeout=120000)
            if resp.ok:
                output.write_bytes(resp.body())
                downloaded=True
        except Exception:
            pass
    if not downloaded:
        try:
            with page.expect_download(timeout=15000) as dl:
                loc=page.get_by_role("button",name="Download")
                loc.first.click(timeout=3000)
            dl.value.save_as(str(output))
            downloaded=True
        except Exception:
            pass
    if not downloaded or not output.exists() or output.stat().st_size < 10000:
        print("google_flow_recover=VIDEO_VISIBLE_NOT_DOWNLOADED")
        raise SystemExit(0)
    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    print("google_flow_recover=PASS")
    print("google_flow_recover_output="+str(output))
    print("google_flow_recover_bytes="+str(len(raw)))
    print("google_flow_recover_sha256="+sha)
PY
