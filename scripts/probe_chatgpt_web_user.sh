#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "chatgpt_web_probe=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
CDP_URL="http://127.0.0.1:9222"
STATE_ROOT="$HOME/.local/share/agentos/chatgpt-web"
STATE="$STATE_ROOT/probe-current.json"

test -x "$PY"
mkdir -p "$STATE_ROOT"
chmod 700 "$STATE_ROOT"

"$PY" - "$CDP_URL" "$STATE" <<'PY'
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

cdp_url, state_path = sys.argv[1], Path(sys.argv[2])

def visible_count(page, selector: str) -> int:
    count = 0
    loc = page.locator(selector)
    for i in range(min(loc.count(), 20)):
        try:
            if loc.nth(i).is_visible(timeout=500):
                count += 1
        except Exception:
            pass
    return count

def text_visible(page, pattern: str) -> bool:
    rx = re.compile(pattern, re.I)
    try:
        loc = page.get_by_text(rx)
        for i in range(min(loc.count(), 20)):
            try:
                if loc.nth(i).is_visible(timeout=400):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError("chatgpt_web_no_browser_context")
    context = browser.contexts[0]
    page = context.new_page()
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)

    parsed = urlparse(page.url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"

    composer_selectors = [
        "#prompt-textarea",
        '[data-testid="composer-input"]',
        'textarea',
        '[contenteditable="true"]',
    ]
    composer_visible = any(visible_count(page, selector) > 0 for selector in composer_selectors)
    login_visible = (
        "/auth/login" in path.lower()
        or text_visible(page, r"^(log in|login|登入|登录)$")
    )
    signup_visible = text_visible(page, r"^(sign up|註冊|注册)$")

    if host.endswith("chatgpt.com") and composer_visible:
        state = "READY"
    elif login_visible or signup_visible:
        state = "LOGIN_REQUIRED"
    elif host.endswith("chatgpt.com"):
        state = "CHATGPT_REACHED_NO_COMPOSER"
    else:
        state = "UNEXPECTED_DESTINATION"

    result = {
        "schema": "agentos.chatgpt-web-probe/v1",
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": state,
        "host": host,
        "path_class": "auth" if "/auth/" in path.lower() else ("root" if path == "/" else "chat"),
        "composer_visible": bool(composer_visible),
        "login_visible": bool(login_visible),
        "signup_visible": bool(signup_visible),
        "persistent_context": True,
        "cdp": True,
    }
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(state_path)
    state_path.chmod(0o600)

    print("chatgpt_web_probe=PASS")
    print("chatgpt_web_session_state=" + state)
    print("chatgpt_web_composer_visible=" + str(bool(composer_visible)).lower())
    print("chatgpt_web_persistent_profile=true")
    print("chatgpt_web_cdp=true")
PY
