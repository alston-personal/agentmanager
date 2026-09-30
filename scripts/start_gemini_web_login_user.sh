#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_login=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
STATE_ROOT="$HOME/.local/share/agentos/gemini-web"
mkdir -p "$STATE_ROOT"
chmod 700 "$STATE_ROOT"

"$PY" - "$STATE_ROOT" <<'PY'
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

state_root=Path(sys.argv[1])
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    if not browser.contexts:
        raise RuntimeError('gemini_web_no_browser_context')
    context=browser.contexts[0]
    page=next((x for x in context.pages if 'gemini.google.com' in str(x.url or '') or 'accounts.google.com' in str(x.url or '')),None)
    if page is None:
        page=context.new_page()
        page.goto('https://gemini.google.com/app',wait_until='domcontentloaded',timeout=60000)
    else:
        page.bring_to_front()
        if 'gemini.google.com' not in str(page.url or '') and 'accounts.google.com' not in str(page.url or ''):
            page.goto('https://gemini.google.com/app',wait_until='domcontentloaded',timeout=60000)
    page.wait_for_timeout(1500)
    if 'gemini.google.com' in str(page.url or ''):
        for pattern in ('Sign in','登入','登录'):
            try:
                loc=page.get_by_text(pattern,exact=True)
                if loc.count() and loc.first.is_visible(timeout=300):
                    loc.first.click(timeout=1500)
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass
    try:
        page.screenshot(path=str(state_root/'login-handoff.png'),full_page=False)
        (state_root/'login-handoff.png').chmod(0o600)
    except Exception:
        pass
    print('gemini_web_login=HUMAN_REQUIRED')
    print('gemini_web_login_page='+str(page.url or '').split('?',1)[0])
    print('gemini_web_handoff=desktop.remote_view')
    print('gemini_web_novnc_url=http://127.0.0.1:6080/vnc.html')
    print('gemini_web_persistent_profile=true')
PY
