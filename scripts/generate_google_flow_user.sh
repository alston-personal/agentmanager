#!/usr/bin/env bash
set -euo pipefail

EXEC_USER="$(id -un)"
if [ "$EXEC_USER" != "ubuntu" ]; then
  echo "google_flow_generate=WRONG_USER"
  echo "google_flow_executor_user=$EXEC_USER"
  exit 0
fi

ROOT="/home/ubuntu/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
CDP_URL="http://127.0.0.1:9222"
OUT_ROOT="/home/ubuntu/agent-data/artifacts/google-flow"
PROMPT="${AGENTOS_GOOGLE_MEDIA_PROMPT:-A cinematic 8-second shot of a quiet mountain trail at golden hour. A gentle breeze moves the grass and leaves, the camera slowly pushes forward, natural realistic lighting, subtle ambient sound, no text, no logos.}"
if [ ! -x "$PY" ]; then
  echo "google_flow_generate=GUI_PYTHON_MISSING"
  exit 0
fi
if ! curl -fsS --max-time 3 "$CDP_URL/json/version" >/dev/null; then
  echo "google_flow_generate=CDP_UNAVAILABLE"
  exit 0
fi
if ! mkdir -p "$OUT_ROOT"; then
  echo "google_flow_generate=ARTIFACT_ROOT_UNWRITABLE"
  exit 0
fi
chmod 700 "$OUT_ROOT"
echo "google_flow_runtime_preflight=PASS"
PYVER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)"
echo "google_flow_python_version=$PYVER"

ERR_LOG="$(mktemp /tmp/agentos-google-flow-error-XXXXXX.log)"
cleanup_err() { rm -f "$ERR_LOG"; }
trap cleanup_err EXIT
set +e
timeout 900s "$PY" - "$CDP_URL" "$OUT_ROOT" "$PROMPT" 2>"$ERR_LOG" <<'PY'
from __future__ import annotations
import hashlib,json,os,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
print("google_flow_stage=PYTHON_STARTED")
print("google_flow_stage=IMPORT_PLAYWRIGHT")
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
print("google_flow_stage=PLAYWRIGHT_IMPORTED")

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

def visible_candidates(page, selectors):
    for selector in selectors:
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),30)):
                item=loc.nth(i)
                try:
                    if item.is_visible(timeout=250):
                        yield item
                except Exception:
                    pass
        except Exception:
            pass

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
        'textarea[placeholder*="describe" i]',
        'textarea[placeholder*="prompt" i]',
        '[contenteditable="true"][aria-label*="prompt" i]',
        '[contenteditable="true"][aria-label*="describe" i]',
        'textarea',
        '[contenteditable="true"]',
    ]
    for item in visible_candidates(page,selectors):
        return item
    return None

def save_debug(page,name):
    path=run_dir/f"{name}.png"
    try:
        page.screenshot(path=str(path),full_page=True)
    except Exception:
        return None
    return path

def ui_control_summary(page):
    out=[]
    selectors=[
        ("button","button"),
        ("link","a"),
        ("textarea","textarea"),
        ("contenteditable",'[contenteditable="true"]'),
        ("textbox",'input[type="text"]'),
    ]
    for kind,selector in selectors:
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),20)):
                item=loc.nth(i)
                try:
                    if not item.is_visible(timeout=150):
                        continue
                    label=(item.get_attribute("aria-label") or item.get_attribute("placeholder") or item.inner_text(timeout=300) or "").strip()
                    label=re.sub(r"\s+"," ",label)[:120]
                    if label:
                        out.append(f"{kind}:{label}")
                except Exception:
                    pass
        except Exception:
            pass
    return out[:40]

with sync_playwright() as p:
    print("google_flow_stage=CONNECT_CDP")
    browser=p.chromium.connect_over_cdp(cdp_url)
    print("google_flow_stage=CDP_CONNECTED")
    if not browser.contexts:
        raise RuntimeError("google_flow_no_browser_context")
    ctx=browser.contexts[0]
    page=next((x for x in ctx.pages if "flow.google.com" in str(x.url or "") or "accounts.google.com" in str(x.url or "")),None)
    if page is None:
        page=ctx.new_page()
    print("google_flow_stage=NAVIGATE_FLOW")
    page.goto("https://flow.google.com/",wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(5000)

    print("google_flow_stage=FLOW_LOADED")
    host=(urlparse(page.url).hostname or "").lower()
    body=text_blob(page).lower()
    login_markers=("sign in","choose an account","登入","登录","使用 google 帳戶","使用 google 账号")
    if host.endswith("accounts.google.com") or any(x in body for x in login_markers):
        save_debug(page,"auth-required")
        print("google_flow_generate=AUTH_REQUIRED")
        print("google_flow_host="+host)
        raise SystemExit(0)

    # Enter an existing project or create a new one.
    if find_prompt(page) is None:
        click_text(page,[r"new project",r"new",r"create.*project",r"start.*project",r"新增.*專案",r"建立.*專案",r"新增",r"建立"])
        page.wait_for_timeout(4000)

    box=find_prompt(page)
    if box is not None:
        print("google_flow_stage=PROMPT_READY")
    if box is None:
        save_debug(page,"no-prompt")
        controls=ui_control_summary(page)
        if controls:
            print("google_flow_ui_controls="+json.dumps(controls,ensure_ascii=False,separators=(",",":")))
        print("google_flow_generate=UI_UNRECOGNIZED")
        print("google_flow_host="+host)
        raise SystemExit(0)

    # Switch from default Image to Video if the control is present.
    click_text(page,[r"nano banana",r"image",r"圖片",r"影像"],timeout_ms=1800)
    page.wait_for_timeout(800)
    click_text(page,[r"^video$",r"影片"],timeout_ms=1800)
    page.wait_for_timeout(1200)

    try:
        box.click(timeout=2000)
        box.fill(prompt,timeout=5000)
    except Exception:
        box.click(timeout=2000)
        page.keyboard.press("Control+A")
        page.keyboard.type(prompt,delay=1)

    save_debug(page,"before-generate")
    print("google_flow_stage=PROMPT_FILLED")

    generated=False
    if click_text(page,[r"generate",r"create",r"生成",r"產生"],timeout_ms=3000):
        generated=True
    if not generated:
        try:
            box.press("Control+Enter")
            generated=True
        except Exception:
            pass

    if not generated:
        print("google_flow_generate=GENERATE_CONTROL_NOT_FOUND")
        raise SystemExit(0)

    print("google_flow_stage=GENERATE_TRIGGERED")
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
            print("google_flow_generate=GENERATION_FAILED")
            raise SystemExit(0)

    if video is None:
        save_debug(page,"generation-timeout")
        print("google_flow_generate=TIMEOUT")
        raise SystemExit(0)

    print("google_flow_stage=VIDEO_VISIBLE")
    save_debug(page,"generated")
    src=str(video.get_attribute("src") or "")
    output=run_dir/"google-flow.mp4"
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
        # Try the provider download UI around the generated result.
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
        print("google_flow_generate=GENERATED_NOT_DOWNLOADED")
        print("google_flow_video_visible=true")
        print("google_flow_artifact_root="+str(run_dir))
        raise SystemExit(0)

    raw=output.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    receipt={
        "schema":"agentos.google-flow-generation-receipt/v1",
        "state":"READY",
        "output":str(output),
        "bytes":len(raw),
        "sha256":sha,
        "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
        "observed_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
    }
    (run_dir/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print("google_flow_generate=PASS")
    print("google_flow_output="+str(output))
    print("google_flow_bytes="+str(len(raw)))
    print("google_flow_sha256="+sha)
    print("google_flow_artifact_root="+str(run_dir))
PY
PY_RC=$?
set -e
if [ "$PY_RC" -ne 0 ]; then
  class="UNKNOWN"
  if grep -Eqi 'TargetClosedError|browser.*closed|context.*closed' "$ERR_LOG"; then
    class="BROWSER_CONTEXT_LOST"
  elif grep -Eqi 'connect_over_cdp|ECONNREFUSED|Connection refused|CDP' "$ERR_LOG"; then
    class="CDP_ATTACH_FAILED"
  elif grep -Eqi 'TimeoutError|timed out|timeout' "$ERR_LOG"; then
    class="PLAYWRIGHT_TIMEOUT"
  elif grep -Eqi 'net::ERR|navigation|Page\.goto' "$ERR_LOG"; then
    class="NAVIGATION_ERROR"
  elif grep -Eqi 'Traceback|AttributeError|TypeError|NameError|ValueError|RuntimeError' "$ERR_LOG"; then
    class="SCRIPT_RUNTIME_ERROR"
  fi
  diag="$(sha256sum "$ERR_LOG" | awk '{print $1}')"
  exc_type="$(python3 - "$ERR_LOG" <<'PYERR'
import re,sys
lines=open(sys.argv[1],encoding='utf-8',errors='replace').read().splitlines()
value='UNKNOWN'
for line in reversed(lines[-40:]):
    m=re.match(r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):', line.strip())
    if m:
        value=m.group(1)[:120]
        break
print(value)
PYERR
)"
  syntax_line=""
  syntax_offset=""
  if [[ "$exc_type" == "SyntaxError" ]]; then
    syntax_line="$(python3 - "$ERR_LOG" <<'PYSL'
import re,sys
text=open(sys.argv[1],encoding='utf-8',errors='replace').read()
m=re.search(r'File "<stdin>", line ([0-9]+)',text)
print(m.group(1) if m else "")
PYSL
)"
    syntax_source="$(python3 - "$ERR_LOG" <<'PYSS'
import re,sys
text=open(sys.argv[1],encoding='utf-8',errors='replace').read()
m=re.search(r'File "([^"]+)", line [0-9]+',text)
src=m.group(1) if m else ""
if src == "<stdin>":
    print("STDIN")
elif "site-packages" in src or "dist-packages" in src:
    print("DEPENDENCY")
elif src:
    print("OTHER")
else:
    print("UNKNOWN")
PYSS
)"
    syntax_offset="$(python3 - "$ERR_LOG" <<'PYSO'
import re,sys
lines=open(sys.argv[1],encoding='utf-8',errors='replace').read().splitlines()
value=''
for i,line in enumerate(lines):
    if line.strip() == '^' and i > 0:
        value=str(max(1,len(lines[i-1])-len(lines[i-1].lstrip())+1))
print(value)
PYSO
)"
  fi
  echo "google_flow_generate=RUNTIME_ERROR"
  echo "google_flow_runtime_error_class=$class"
  echo "google_flow_runtime_exception_type=$exc_type"
  if [[ -n "$syntax_line" ]]; then echo "google_flow_runtime_syntax_line=$syntax_line"; fi
  if [[ -n "$syntax_source" ]]; then echo "google_flow_runtime_syntax_source=$syntax_source"; fi
  if [[ -n "$syntax_offset" ]]; then echo "google_flow_runtime_syntax_offset=$syntax_offset"; fi
  echo "google_flow_runtime_error_sha256=$diag"
  exit 0
fi
