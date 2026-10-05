#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "google_vids_generate=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
CDP_URL="http://127.0.0.1:9222"
OUT_ROOT="/home/ubuntu/agent-data/artifacts/google-vids"
PROMPT="${AGENTOS_GOOGLE_MEDIA_PROMPT:-A cinematic 8-second shot of a quiet mountain trail at golden hour. A gentle breeze moves the grass and leaves, the camera slowly pushes forward, natural realistic lighting, subtle ambient sound, no text, no logos.}"
test -x "$PY"
mkdir -p "$OUT_ROOT"
chmod 700 "$OUT_ROOT"

timeout 900s "$PY" - "$CDP_URL" "$OUT_ROOT" "$PROMPT" <<'PY'
from __future__ import annotations
import hashlib,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

cdp_url,out_root,prompt=sys.argv[1],Path(sys.argv[2]),sys.argv[3]
if not (1 <= len(prompt) <= 1600):
    raise ValueError("prompt_length_invalid")

stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_dir=out_root/stamp
run_dir.mkdir(parents=True,exist_ok=True)

def text_blob(page):
    try:
        return page.locator("body").inner_text(timeout=3000)[:30000]
    except Exception:
        return ""

def click_text(page, patterns, timeout_ms=2500):
    for pat in patterns:
        rgx=re.compile(pat,re.I)
        for role in ("button","link","menuitem","tab"):
            try:
                loc=page.get_by_role(role,name=rgx)
                for i in range(min(loc.count(),12)):
                    item=loc.nth(i)
                    try:
                        if item.is_visible(timeout=300):
                            item.click(timeout=timeout_ms)
                            return True
                    except Exception:
                        pass
        try:
            loc=page.get_by_text(rgx,exact=False)
            for i in range(min(loc.count(),12)):
                item=loc.nth(i)
                try:
                    if item.is_visible(timeout=300):
                        item.click(timeout=timeout_ms)
                        return True
                except Exception:
                    pass
        except Exception:
            pass
    return False

def find_prompt(page):
    selectors=[
        'textarea[placeholder*="prompt" i]',
        'textarea[placeholder*="describe" i]',
        '[contenteditable="true"][aria-label*="prompt" i]',
        '[contenteditable="true"][aria-label*="describe" i]',
        'textarea',
        '[contenteditable="true"]',
    ]
    for selector in selectors:
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),30)):
                item=loc.nth(i)
                try:
                    if item.is_visible(timeout=250):
                        return item
                except Exception:
                    pass
        except Exception:
            pass
    return None

def save_debug(page,name):
    path=run_dir/f"{name}.png"
    try:
        page.screenshot(path=str(path),full_page=True)
    except Exception:
        return None
    return path

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError("google_vids_no_browser_context")
    ctx=browser.contexts[0]
    page=next((x for x in ctx.pages if "vids.google.com" in str(x.url or "") or "docs.google.com/videos" in str(x.url or "") or "accounts.google.com" in str(x.url or "")),None)
    if page is None:
        page=ctx.new_page()

    page.goto("https://vids.google.com/",wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(5000)
    host=(urlparse(page.url).hostname or "").lower()
    body=text_blob(page).lower()
    login_markers=("sign in","choose an account","登入","登录","使用 google 帳戶","使用 google 账号")
    if host.endswith("accounts.google.com") or any(x in body for x in login_markers):
        save_debug(page,"auth-required")
        print("google_vids_generate=AUTH_REQUIRED")
        print("google_vids_host="+host)
        raise SystemExit(0)

    # Start the AI-video flow from the landing/start menu.
    click_text(page,[r"create ai videos",r"create ai video",r"製作 ai 影片",r"建立 ai 影片",r"ai video"],timeout_ms=3000)
    page.wait_for_timeout(4000)

    # Some accounts open a blank Vid first; use the AI Video sidebar entry.
    box=find_prompt(page)
    if box is None:
        click_text(page,[r"ai video",r"ai 影片",r"generate video",r"生成影片"],timeout_ms=2500)
        page.wait_for_timeout(2500)
        click_text(page,[r"^create$",r"^generate$",r"建立",r"生成"],timeout_ms=1800)
        page.wait_for_timeout(1500)
        box=find_prompt(page)

    if box is None:
        save_debug(page,"no-prompt")
        print("google_vids_generate=UI_UNRECOGNIZED")
        print("google_vids_host="+host)
        raise SystemExit(0)

    try:
        box.click(timeout=2000)
        box.fill(prompt,timeout=5000)
    except Exception:
        box.click(timeout=2000)
        page.keyboard.press("Control+A")
        page.keyboard.type(prompt,delay=1)

    save_debug(page,"before-generate")
    generated=click_text(page,[r"^generate$",r"^create$",r"生成",r"產生",r"建立"],timeout_ms=3000)
    if not generated:
        try:
            box.press("Control+Enter")
            generated=True
        except Exception:
            pass
    if not generated:
        print("google_vids_generate=GENERATE_CONTROL_NOT_FOUND")
        raise SystemExit(0)

    deadline=time.monotonic()+720
    video=None
    while time.monotonic()<deadline:
        page.wait_for_timeout(5000)
        try:
            vids=page.locator("video")
            for i in range(min(vids.count(),12)):
                item=vids.nth(i)
                try:
                    if item.is_visible(timeout=300):
                        video=item
                        break
                except Exception:
                    pass
        except Exception:
            pass
        if video is not None:
            break
        low=text_blob(page).lower()
        if any(x in low for x in ("generation failed","couldn't generate","無法生成","產生失敗","failed to generate")):
            save_debug(page,"generation-failed")
            print("google_vids_generate=GENERATION_FAILED")
            raise SystemExit(0)

    if video is None:
        save_debug(page,"generation-timeout")
        print("google_vids_generate=TIMEOUT")
        raise SystemExit(0)

    save_debug(page,"generated")
    src=str(video.get_attribute("src") or "")
    output=run_dir/"google-vids.mp4"
    downloaded=False
    if src.startswith("http://") or src.startswith("https://"):
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
                ok=click_text(page,[r"download",r"下載"],timeout_ms=3000)
                if not ok:
                    raise RuntimeError("download_control_not_found")
            dl.value.save_as(str(output))
            downloaded=True
        except Exception:
            pass

    if not downloaded or not output.is_file() or output.stat().st_size < 10000:
        print("google_vids_generate=GENERATED_NOT_DOWNLOADED")
        print("google_vids_video_visible=true")
        print("google_vids_artifact_root="+str(run_dir))
        raise SystemExit(0)

    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    receipt={
        "schema":"agentos.google-vids-generation-receipt/v1",
        "state":"READY",
        "output":str(output),
        "bytes":len(raw),
        "sha256":sha,
        "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
        "observed_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
    }
    (run_dir/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print("google_vids_generate=PASS")
    print("google_vids_output="+str(output))
    print("google_vids_bytes="+str(len(raw)))
    print("google_vids_sha256="+sha)
    print("google_vids_artifact_root="+str(run_dir))
PY
