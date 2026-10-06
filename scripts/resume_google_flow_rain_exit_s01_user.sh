#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "google_flow_rain_exit_resume=WRONG_USER"
  exit 2
fi

PY="$HOME/.local/share/agentos/gui-worker/venv/bin/python"
OUT_ROOT="/home/ubuntu/agent-data/artifacts/vision-studio/rain-exit-v001/resume-s01"
test -x "$PY"
mkdir -p "$OUT_ROOT"

"$PY" - "$OUT_ROOT" <<'PY'
from __future__ import annotations
import hashlib,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_URL="https://flow.google.com/project/7c7d201a-ee6f-40e1-aa4c-2309c9543237"
EXPECTED_MARKERS=("taipei","metro","umbrella","mio")
out_root=Path(sys.argv[1])
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_dir=out_root/stamp
run_dir.mkdir(parents=True,exist_ok=True)

print("google_flow_rain_exit_stage=CONNECT_CDP",flush=True)
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=10000)
    ctx=browser.contexts[0]
    page=next((x for x in ctx.pages if PROJECT_URL in str(x.url or "")),None)
    if page is None:
        page=ctx.new_page()
        page.goto(PROJECT_URL,wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(5000)
    print("google_flow_rain_exit_stage=PROJECT_LOADED",flush=True)
    print("google_flow_rain_exit_url="+str(page.url or "")[:500])

    body=(page.locator("body").inner_text(timeout=4000) or "")
    low=body.lower()
    if not all(m in low for m in EXPECTED_MARKERS):
        print("google_flow_rain_exit_resume=PROJECT_MISMATCH")
        raise SystemExit(0)
    print("google_flow_rain_exit_project_match=PASS")

    approval_text=("要開始生成這 1 部影片嗎" in body or
                   "start generating this 1 video" in low or
                   "this will cost 15" in low or
                   "這會消耗 15 點" in body)
    if not approval_text:
        # If already approved earlier, allow resume only if generation/result
        # state is present. Never create a new prompt or press Start Generate.
        if not any(x in low for x in ("正在生成","generating","生成中","影片")):
            print("google_flow_rain_exit_resume=APPROVAL_PROMPT_NOT_FOUND")
            raise SystemExit(0)
    else:
        print("google_flow_rain_exit_stage=APPROVAL_READY")
        approved=False
        for label in ("核准","Approve"):
            try:
                loc=page.get_by_role("button",name=label,exact=True)
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click(timeout=3000)
                    approved=True
                    break
            except Exception:
                pass
        if not approved:
            # Avoid "一律核准" / "Always approve".
            try:
                loc=page.get_by_text("核准",exact=True)
                if loc.count():
                    loc.first.click(timeout=3000)
                    approved=True
            except Exception:
                pass
        if not approved:
            print("google_flow_rain_exit_resume=APPROVE_CONTROL_NOT_FOUND")
            raise SystemExit(0)
        print("google_flow_rain_exit_stage=APPROVED_ONCE",flush=True)
        page.wait_for_timeout(2500)

    deadline=time.monotonic()+900
    video=None
    while time.monotonic()<deadline:
        page.wait_for_timeout(5000)
        body=(page.locator("body").inner_text(timeout=2500) or "")
        low=body.lower()
        vids=page.locator("video")
        for i in range(min(vids.count(),20)):
            item=vids.nth(i)
            try:
                if item.is_visible(timeout=300):
                    context=str(item.evaluate("""el => {
                      let n=el;
                      for(let i=0;i<6 && n;i++,n=n.parentElement){
                        const t=(n.innerText||'').trim();
                        if(t) return t.slice(0,700);
                      }
                      return '';
                    }""") or "")
                    c=context.lower()
                    if any(m in c for m in ("taipei","metro","umbrella","mio","台北","捷運","雨傘")) or all(m in low for m in EXPECTED_MARKERS):
                        video=item
                        break
            except Exception:
                pass
        if video is not None:
            break
        if any(x in low for x in ("generation failed","couldn't generate","failed to generate","產生失敗","生成失敗","無法生成")):
            print("google_flow_rain_exit_resume=GENERATION_FAILED")
            raise SystemExit(0)

    if video is None:
        print("google_flow_rain_exit_resume=GENERATION_TIMEOUT")
        raise SystemExit(0)

    print("google_flow_rain_exit_stage=VIDEO_VISIBLE",flush=True)
    output=run_dir/"rain-exit-s01.mp4"
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

    downloaded=False
    for media_url in candidates:
        if not media_url.startswith(("http://","https://")):
            continue
        try:
            resp=ctx.request.get(media_url,timeout=120000)
            if resp.ok and len(resp.body())>=10000:
                output.write_bytes(resp.body())
                downloaded=True
                break
        except Exception:
            pass

    if not downloaded:
        blob_url=next((x for x in candidates if x.startswith("blob:")),None)
        if blob_url:
            try:
                with page.expect_download(timeout=20000) as dl:
                    page.evaluate("""(u) => {
                      const a=document.createElement('a');
                      a.href=u; a.download='rain-exit-s01.mp4';
                      document.body.appendChild(a); a.click(); a.remove();
                    }""",blob_url)
                dl.value.save_as(str(output))
                downloaded=True
            except Exception:
                pass

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

    if not downloaded or not output.exists() or output.stat().st_size<10000:
        print("google_flow_rain_exit_resume=VIDEO_VISIBLE_NOT_DOWNLOADED")
        raise SystemExit(0)

    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    print("google_flow_rain_exit_resume=PASS")
    print("google_flow_rain_exit_output="+str(output))
    print("google_flow_rain_exit_bytes="+str(len(raw)))
    print("google_flow_rain_exit_sha256="+sha)
PY
