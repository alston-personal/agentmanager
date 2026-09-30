from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from agentos_node.web_agent_surface import (
    WebSurfaceAdapter,
    body_text,
    first_visible,
    stable_session_id,
    title,
)

PROVIDER = "gemini-web"
ROOT = Path(os.environ.get("AGENTOS_GEMINI_WEB_BRIDGE") or (Path.home() / ".local/share/agentos/gemini-web/bridge")).expanduser()
CDP_URL = os.environ.get("AGENTOS_GUI_CDP_URL") or "http://127.0.0.1:9222"

COMPOSERS = (
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
)


def classify(page):
    url = str(page.url or "")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    composer = first_visible(page, COMPOSERS)
    text = body_text(page).lower()

    if host.endswith("gemini.google.com") and composer is not None:
        state = "READY"
    elif host.endswith("accounts.google.com"):
        state = "LOGIN_REQUIRED"
    elif host.endswith("gemini.google.com") and any(marker in text for marker in (
        "sign in", "登入", "登录", "choose an account", "使用 google 帳戶",
    )):
        state = "LOGIN_REQUIRED"
    elif host.endswith("gemini.google.com"):
        state = "GEMINI_REACHED_NO_COMPOSER"
    else:
        state = "UNEXPECTED_DESTINATION"

    parts = [part for part in path.split("/") if part]
    preferred = None
    if parts and parts[0] == "app" and len(parts) > 1:
        preferred = parts[1]
    return {
        "session_id": stable_session_id("gemini", url, preferred),
        "url": url,
        "title": title(page),
        "state": state,
        "composer_visible": composer is not None,
    }


def harvest(page):
    selectors = (
        'model-response',
        '[data-test-id*="model-response"]',
        '.model-response-text',
        'message-content',
    )
    rows = []
    seen = set()
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(max(0, loc.count() - 8), loc.count()):
                try:
                    value = loc.nth(i).inner_text(timeout=1000).strip()[:6000]
                except Exception:
                    continue
                if value and value not in seen:
                    seen.add(value)
                    rows.append(value)
        except Exception:
            pass
    return rows[-5:]


ADAPTER = WebSurfaceAdapter(
    provider=PROVIDER,
    root=ROOT,
    hosts=("gemini.google.com", "accounts.google.com"),
    composer_selectors=COMPOSERS,
    classify=classify,
    harvest=harvest,
    cdp_url=CDP_URL,
)


def serve(interval: float = 0.5) -> None:
    ADAPTER.write_descriptor()
    while True:
        ADAPTER.run_once()
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.serve:
        serve()
        return 0
    ADAPTER.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
