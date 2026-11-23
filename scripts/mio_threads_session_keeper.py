#!/usr/bin/env python3
"""Mio Threads Session Keeper & Health Diagnostic.

1. Inspects whether Mio's persistent browser (port 9224) has an authenticated Threads session.
2. If authenticated, refreshes the persistent backup in $AGENT_DATA_ROOT/secrets/mio-threads-session/cookies.json.
3. If unauthenticated but backup cookies exist, automatically restores them into the browser context.
4. Performs a lightweight keep-alive heartbeat to maintain session validity on Meta edge.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

CDP_URL = os.environ.get("AGENTOS_MIO_CDP", "http://127.0.0.1:9224")
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
SECRETS_DIR = DATA_ROOT / "secrets" / "mio-threads-session"
COOKIE_BACKUP = SECRETS_DIR / "cookies.json"

def main() -> int:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL, timeout=5000)
            ctx = browser.contexts[0]
            cookies = ctx.cookies()
            has_session = any(c.get("name") == "sessionid" and "threads" in c.get("domain", "") for c in cookies)

            if not has_session and COOKIE_BACKUP.is_file():
                try:
                    saved_cookies = json.loads(COOKIE_BACKUP.read_text(encoding="utf-8"))
                    ctx.add_cookies(saved_cookies)
                    print("mio_session_keeper=RESTORED_FROM_BACKUP")
                    has_session = True
                except Exception as e:
                    print(f"mio_session_keeper=BACKUP_RESTORE_FAILED error={e}")

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.threads.com/@mio.milkcat", wait_until="commit", timeout=15000)
            page.wait_for_timeout(2000)
            
            # Verify Edit profile button exists (proves authenticated own profile)
            body = page.locator("body").inner_text()[:2000]
            is_authenticated = "Edit profile" in body or "View insights" in body or "What’s new?" in body

            if is_authenticated:
                fresh_cookies = ctx.cookies()
                COOKIE_BACKUP.write_text(json.dumps(fresh_cookies, indent=2, ensure_ascii=False), encoding="utf-8")
                print("mio_session_keeper=PASS status=AUTHENTICATED cookies_synced=" + str(len(fresh_cookies)))
                return 0
            else:
                print("mio_session_keeper=LOGIN_REQUIRED status=UNAUTHENTICATED")
                return 1
    except Exception as exc:
        print(f"mio_session_keeper=ERROR error_type={type(exc).__name__} error={exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
