#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_probe=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"

"$PY" - <<'PY'
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

state='UNKNOWN'
final_url=''
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    assert browser.contexts
    ctx=browser.contexts[0]
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://www.threads.com/messages',wait_until='domcontentloaded',timeout=25000)
    page.wait_for_timeout(2500)
    final_url=page.url
    body=(page.locator('body').inner_text(timeout=5000) or '')[:12000]
    low=(final_url+'\n'+body).lower()
    if '/login' in final_url or 'accountscenter' in low or 'log in' in low or '登入' in body:
        state='LOGIN_REQUIRED'
    elif 'try again later' in low or 'restrict certain activity' in low or '稍後再試' in body:
        state='BLOCKED'
    elif '/messages' in final_url:
        state='AUTHENTICATED'
    else:
        state='UNKNOWN'

root=Path('/home/ubuntu/agent-data/runtime/social/threads-web-dm')
root.mkdir(parents=True,exist_ok=True)
os.chmod(root,0o700)
out=root/'login-probe.json'
out.write_text(json.dumps({
    'schema':'agentos.threads-web-dm-login-probe/v2',
    'mode':'oracle_gui_worker',
    'session_state':state,
},sort_keys=True,indent=2)+'\n',encoding='utf-8')
os.chmod(out,0o600)

print('threads_web_dm_login_probe=PASS')
print('threads_web_dm_login_mode=oracle_gui_worker')
print('threads_web_dm_login_session_state='+state)
PY
