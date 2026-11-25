from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from agent_core.active_continuation import read_active_continuation
from agentos_node.one_mcp import OracleLocalGateway

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
    is_gemini = host.endswith("gemini.google.com")
    is_accounts = host.endswith("accounts.google.com")
    if not (is_gemini or is_accounts):
        return {
            "session_id": stable_session_id("gemini", url),
            "url": url,
            "title": "",
            "state": "UNEXPECTED_DESTINATION",
            "composer_visible": False,
        }

    composer = first_visible(page, COMPOSERS)
    text = body_text(page).lower()

    if is_gemini and composer is not None:
        state = "READY"
    elif is_accounts:
        state = "LOGIN_REQUIRED"
    elif is_gemini and any(marker in text for marker in (
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


def build_web_executor_preamble(gateway: OracleLocalGateway | None = None) -> str:
    """Build canonical AgentOS Executor bootstrap preamble for Gemini Web."""
    try:
        gw = gateway or OracleLocalGateway()
        active = read_active_continuation(gw.data_root)
        project_id = str(active.get("project_id") or "agentos-core")
        res = gw.resolve(project_id)
        ir = (res.get("continuation") or {}).get("canonical_ir") or {}
        goal = ir.get("goal") or "協助 AgentOS 雙代理審核、文字創作與系統任務執行"
    except Exception:
        project_id = "agentos-core"
        goal = "協助 AgentOS 眾神殿進行代碼審查與雙代理驗證"

    return (
        f"[AgentOS ONE Session Hook - Executor Registration]\n"
        f"你目前作為 AgentOS 系統的在席 Web Executor (Oracle Node, surface: gemini-web)。\n"
        f"所屬專案: {project_id}\n"
        f"當前目標: {goal}\n"
        f"身份職責: 依據 AgentOS 眾神殿與憲法體制，負責執行指示、審核代碼、文字生成與提供雙代理交叉審查意見。\n"
        f"請確認你的 Executor 身份，並在被詢問時明確表明你是 AgentOS Web Executor。"
    )


BOOTSTRAPPED_SESSIONS: set[str] = set()


def on_session_attach_hook(page: Any, session_row: dict[str, Any]) -> dict[str, Any]:
    """Auto-hook executed when a Gemini Web session is attached."""
    session_id = str(session_row.get("session_id") or "")
    if not session_id or session_id in BOOTSTRAPPED_SESSIONS:
        return {"status": "already_bootstrapped", "session_id": session_id}

    if session_row.get("state") != "READY":
        return {"status": "skipped_not_ready", "session_id": session_id}

    composer = first_visible(page, COMPOSERS)
    if composer is None:
        return {"status": "composer_not_visible", "session_id": session_id}

    preamble = build_web_executor_preamble()
    try:
        composer.fill(preamble)
    except Exception:
        try:
            composer.click()
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.type(preamble)
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:300], "session_id": session_id}

    try:
        page.keyboard.press("Enter")
    except Exception as exc:
        return {"status": "error_submitting", "error": str(exc)[:300], "session_id": session_id}

    BOOTSTRAPPED_SESSIONS.add(session_id)
    return {"status": "bootstrapped", "session_id": session_id, "preamble_len": len(preamble)}


ADAPTER = WebSurfaceAdapter(
    provider=PROVIDER,
    root=ROOT,
    hosts=("gemini.google.com", "accounts.google.com"),
    composer_selectors=COMPOSERS,
    classify=classify,
    harvest=harvest,
    cdp_url=CDP_URL,
    preflight_target_inventory=True,
    connect_timeout_ms=5000,
    raw_cdp_fallback=True,
    on_session_attach=on_session_attach_hook,
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
