#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_mio_login_resume=WRONG_USER" >&2
  exit 2
fi

python3 - <<'PY'
import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE="http://127.0.0.1:9222"
TARGET_ACCOUNT="mio.milkcat"
INBOX="https://www.threads.com/messages"

def is_login(url: str) -> bool:
    p=urlparse(url)
    path=(p.path or "").lower()
    host=(p.hostname or "").lower()
    return path=="/login" or path.startswith("/login/") or "accountscenter" in host

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(BASE, timeout=5000)
    assert browser.contexts
    ctx=browser.contexts[0]
    page=ctx.new_page()
    try:
        page.goto(INBOX, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        if not is_login(page.url):
            print("threads_mio_login_resume=PASS")
            print("threads_mio_login_resume_state=ALREADY_AUTHENTICATED")
            raise SystemExit(0)

        body=(page.locator("body").inner_text(timeout=5000) or "")[:16000]
        low=body.lower()
        account_hint=(TARGET_ACCOUNT in low) or ("@"+TARGET_ACCOUNT in low)
        print("threads_mio_login_resume_account_hint="+str(account_hint).lower())
        if not account_hint:
            print("threads_mio_login_resume=HUMAN_REQUIRED")
            print("threads_mio_login_resume_reason=ACCOUNT_HINT_MISSING")
            raise SystemExit(0)

        patterns=[
            re.compile(r"continue as.*mio\.milkcat", re.I),
            re.compile(r"繼續以.*mio\.milkcat", re.I),
            re.compile(r"繼續使用.*mio\.milkcat", re.I),
        ]
        candidate=None
        for role in ("button","link"):
            for pat in patterns:
                loc=page.get_by_role(role, name=pat)
                try:
                    if loc.count()>0 and loc.first.is_visible():
                        candidate=loc.first
                        break
                except Exception:
                    pass
            if candidate is not None:
                break

        if candidate is None:
            print("threads_mio_login_resume=HUMAN_REQUIRED")
            print("threads_mio_login_resume_reason=RESUME_CONTROL_MISSING")
            raise SystemExit(0)

        candidate.click(timeout=5000)
        for _ in range(20):
            page.wait_for_timeout(500)
            if not is_login(page.url):
                print("threads_mio_login_resume=PASS")
                print("threads_mio_login_resume_state=RESUMED")
                raise SystemExit(0)

        print("threads_mio_login_resume=HUMAN_REQUIRED")
        print("threads_mio_login_resume_reason=RESUME_DID_NOT_AUTHENTICATE")
    finally:
        page.close()
PY
