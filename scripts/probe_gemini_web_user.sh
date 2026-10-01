#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_probe=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
CDP_URL="http://127.0.0.1:9222"
STATE_ROOT="$HOME/.local/share/agentos/gemini-web"
STATE="$STATE_ROOT/probe-current.json"

test -x "$PY"
mkdir -p "$STATE_ROOT"
chmod 700 "$STATE_ROOT"

BRIDGE_ROOT="$HOME/.local/share/agentos/gemini-web/bridge"
if [ -s "$BRIDGE_ROOT/bridge.json" ] && [ -s "$BRIDGE_ROOT/sessions.json" ]; then
  if "$PY" - "$BRIDGE_ROOT/sessions.json" "$STATE" <<'PY'
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse

sessions_path,state_path=Path(sys.argv[1]),Path(sys.argv[2])
doc=json.loads(sessions_path.read_text(encoding='utf-8-sig'))
observed=str(doc.get('observed_at') or '')
try:
    ts=datetime.fromisoformat(observed.replace('Z','+00:00')).astimezone(timezone.utc)
except ValueError:
    raise SystemExit(3)
age=max(0.0,(datetime.now(timezone.utc)-ts).total_seconds())
sessions=[x for x in (doc.get('sessions') or []) if isinstance(x,dict)]
if age > 20 or not sessions:
    raise SystemExit(3)

preferred=next((x for x in sessions if x.get('state')=='READY'),None)
if preferred is None:
    preferred=next((x for x in sessions if x.get('state')=='LOGIN_REQUIRED'),None)
if preferred is None:
    preferred=sessions[0]
state=str(preferred.get('state') or 'UNKNOWN')
parsed=urlparse(str(preferred.get('url') or ''))
host=(parsed.hostname or '').lower()
path=parsed.path or '/'
result={
    'schema':'agentos.gemini-web-probe/v1',
    'observed_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
    'state':state,
    'host':host,
    'path_class':'app' if path.startswith('/app') else ('auth' if host.endswith('accounts.google.com') else 'other'),
    'composer_visible':bool(preferred.get('composer_visible')),
    'persistent_context':True,
    'cdp':True,
    'source':'bridge_snapshot',
    'bridge_snapshot_age_seconds':round(age,3),
}
tmp=state_path.with_suffix('.tmp')
tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
tmp.chmod(0o600)
tmp.replace(state_path)
state_path.chmod(0o600)
print('gemini_web_probe=PASS')
print('gemini_web_session_state='+state)
print('gemini_web_composer_visible='+str(bool(preferred.get('composer_visible'))).lower())
print('gemini_web_persistent_profile=true')
print('gemini_web_cdp=true')
print('gemini_web_probe_source=bridge_snapshot')
PY
  then
    exit 0
  fi
fi

# Compatibility/bootstrap fallback only. Keep it bounded so one bad browser
# surface cannot monopolize the oracle-gui scheduler lane for two minutes.
timeout 45s "$PY" - "$CDP_URL" "$STATE" <<'PY'
from __future__ import annotations
import json,re,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

cdp_url,state_path=sys.argv[1],Path(sys.argv[2])

def first_visible(page,selectors):
    for selector in selectors:
        try:
            loc=page.locator(selector)
            for i in range(min(loc.count(),12)):
                item=loc.nth(i)
                try:
                    if item.is_visible(timeout=300):
                        return item
                except Exception:
                    pass
        except Exception:
            pass
    return None

selectors=[
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError('gemini_web_no_browser_context')
    context=browser.contexts[0]
    page=next((x for x in context.pages if 'gemini.google.com' in str(x.url or '') or 'accounts.google.com' in str(x.url or '')),None)
    if page is None:
        page=context.new_page()
    if 'gemini.google.com' not in str(page.url or '') and 'accounts.google.com' not in str(page.url or ''):
        page.goto('https://gemini.google.com/app',wait_until='domcontentloaded',timeout=60000)
    else:
        try:
            page.bring_to_front()
        except Exception:
            pass
    page.wait_for_timeout(3500)

    parsed=urlparse(str(page.url or ''))
    host=(parsed.hostname or '').lower()
    path=parsed.path or '/'
    composer=first_visible(page,selectors)
    try:
        body=page.locator('body').inner_text(timeout=1500)[:16000].lower()
    except Exception:
        body=''

    login_markers=('sign in','choose an account','登入','登录','使用 google 帳戶','使用 google 账号')
    if host.endswith('gemini.google.com') and composer is not None:
        state='READY'
    elif host.endswith('accounts.google.com') or any(x in body for x in login_markers):
        state='LOGIN_REQUIRED'
    elif host.endswith('gemini.google.com'):
        state='GEMINI_REACHED_NO_COMPOSER'
    else:
        state='UNEXPECTED_DESTINATION'

    result={
        'schema':'agentos.gemini-web-probe/v1',
        'observed_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
        'state':state,
        'host':host,
        'path_class':'app' if path.startswith('/app') else ('auth' if host.endswith('accounts.google.com') else 'other'),
        'composer_visible':bool(composer is not None),
        'persistent_context':True,
        'cdp':True,
    }
    tmp=state_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.chmod(0o600)
    tmp.replace(state_path)
    state_path.chmod(0o600)

    print('gemini_web_probe=PASS')
    print('gemini_web_session_state='+state)
    print('gemini_web_composer_visible='+str(bool(composer is not None)).lower())
    print('gemini_web_persistent_profile=true')
    print('gemini_web_cdp=true')
PY
