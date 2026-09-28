#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_start=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"
test -f "$ROOT/capability.json"

"$PY" - <<'PY'
import json, urllib.request
from playwright.sync_api import sync_playwright

with urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=3) as r:
    meta=json.load(r)
assert meta.get('webSocketDebuggerUrl')

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    assert browser.contexts
    ctx=browser.contexts[0]
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    if not page.url.startswith('https://www.threads.com/'):
        page.goto('https://www.threads.com/login',wait_until='domcontentloaded',timeout=20000)
    elif '/messages' not in page.url and '/login' not in page.url:
        page.goto('https://www.threads.com/login',wait_until='domcontentloaded',timeout=20000)
    print('threads_web_dm_login_start=PASS')
    print('threads_web_dm_login_mode=oracle_gui_worker')
    print('threads_web_dm_login_browser_persistent=true')
    print('threads_web_dm_login_remote_view=localhost_only')
PY
