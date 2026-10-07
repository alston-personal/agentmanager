#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_persona_login_resume=WRONG_USER" >&2
  exit 2
fi

PERSONA="${AGENTOS_DM_PERSONA:-}"
case "$PERSONA" in
  mio) ACCOUNT="mio.milkcat"; BASE="http://127.0.0.1:9222" ;;
  oursong) ACCOUNT="oursong_alstonhuang"; BASE="http://127.0.0.1:9223" ;;
  *) echo "threads_persona_login_resume=INVALID_PERSONA" >&2; exit 2 ;;
esac

AGENTOS_RESUME_ACCOUNT="$ACCOUNT" AGENTOS_RESUME_CDP="$BASE" AGENTOS_RESUME_PERSONA="$PERSONA" python3 - <<'PY'
import os,re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

base=os.environ["AGENTOS_RESUME_CDP"]
account=os.environ["AGENTOS_RESUME_ACCOUNT"]
persona=os.environ["AGENTOS_RESUME_PERSONA"]
inbox="https://www.threads.com/messages"

def out(key,value):
    print(f"threads_persona_login_resume_{key}={value}")

def is_login(url):
    p=urlparse(url)
    path=(p.path or "").lower()
    host=(p.hostname or "").lower()
    return path=="/login" or path.startswith("/login/") or "accountscenter" in host

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(base,timeout=5000)
    assert browser.contexts
    ctx=browser.contexts[0]
    page=ctx.new_page()
    try:
        page.goto(inbox,wait_until="domcontentloaded",timeout=30000)
        page.wait_for_timeout(1500)
        if not is_login(page.url):
            out("state","ALREADY_AUTHENTICATED")
            out("persona",persona)
            print("threads_persona_login_resume=PASS")
            raise SystemExit(0)

        body=(page.locator("body").inner_text(timeout=5000) or "")[:16000]
        low=body.lower()
        hint=(account.lower() in low) or (("@"+account).lower() in low)
        out("account_hint",str(hint).lower())
        out("persona",persona)
        if not hint:
            out("reason","ACCOUNT_HINT_MISSING")
            print("threads_persona_login_resume=HUMAN_REQUIRED")
            raise SystemExit(0)

        escaped=re.escape(account)
        patterns=[
            re.compile(r"continue as.*"+escaped,re.I),
            re.compile(r"繼續以.*"+escaped,re.I),
            re.compile(r"繼續使用.*"+escaped,re.I),
        ]
        candidate=None
        for role in ("button","link"):
            for pat in patterns:
                loc=page.get_by_role(role,name=pat)
                try:
                    if loc.count()>0 and loc.first.is_visible():
                        candidate=loc.first
                        break
                except Exception:
                    pass
            if candidate is not None:
                break

        if candidate is None:
            out("reason","RESUME_CONTROL_MISSING")
            print("threads_persona_login_resume=HUMAN_REQUIRED")
            raise SystemExit(0)

        candidate.click(timeout=5000)
        for _ in range(20):
            page.wait_for_timeout(500)
            if not is_login(page.url):
                out("state","RESUMED")
                print("threads_persona_login_resume=PASS")
                raise SystemExit(0)

        out("reason","RESUME_DID_NOT_AUTHENTICATE")
        print("threads_persona_login_resume=HUMAN_REQUIRED")
    finally:
        page.close()
PY
