"""
agent_core/gui_worker_client.py
===============================
AgentOS GUI Worker 輕量查詢客戶端。
當無外部付費 API 且本地 CLI 無法即時調用時，
直接透過 Oracle GUI Worker (CDP :9222) 向已登入且在席之 Web 模型 (ChatGPT Web / Gemini Web)
發送 Prompt 並提取回覆。
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

COMPOSER_SELECTORS = [
    '#prompt-textarea',
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]


def _first_visible(page, selectors: List[str]):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 8)):
                item = loc.nth(i)
                if item.is_visible(timeout=300):
                    return item
        except Exception:
            pass
    return None


def _harvest_responses(page, provider: str = "chatgpt") -> List[str]:
    rows: List[str] = []
    if provider == "chatgpt":
        loc = page.locator('[data-message-author-role="assistant"]')
    else:
        loc = page.locator('model-response, [data-test-id*="model-response"], .model-response-text, message-content')

    try:
        count = loc.count()
        for i in range(max(0, count - 5), count):
            try:
                val = loc.nth(i).inner_text(timeout=1000).strip()
                if val and val not in rows:
                    rows.append(val)
            except Exception:
                continue
    except Exception:
        pass
    return rows


def query_gui_worker(prompt: str, timeout: int = 40) -> Dict[str, Any]:
    """Query GUI Worker browser tab via CDP."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            if not browser.contexts:
                return {"status": "FAIL", "error": "no_browser_context"}

            ctx = browser.contexts[0]
            pages = ctx.pages
            # 優先搜尋 ChatGPT 或 Gemini 分頁
            target_page = None
            provider = "chatgpt"

            for page in pages:
                url = str(page.url or "")
                if "chatgpt.com" in url:
                    target_page = page
                    provider = "chatgpt"
                    break
                elif "gemini.google.com" in url:
                    target_page = page
                    provider = "gemini"
                    break

            if not target_page:
                return {"status": "FAIL", "error": "no_ai_web_tab_found"}

            target_page.bring_to_front()
            composer = _first_visible(target_page, COMPOSER_SELECTORS)
            if composer is None:
                return {"status": "FAIL", "error": "composer_not_visible"}

            initial_responses = _harvest_responses(target_page, provider)
            initial_count = len(initial_responses)

            # 注入 Prompt
            try:
                composer.fill(prompt)
            except Exception:
                composer.click()
                target_page.keyboard.press("ControlOrMeta+A")
                target_page.keyboard.type(prompt)

            target_page.keyboard.press("Enter")

            # 等待回覆
            deadline = time.monotonic() + timeout
            final_text = ""
            while time.monotonic() < deadline:
                time.sleep(2)
                curr_responses = _harvest_responses(target_page, provider)
                if len(curr_responses) > initial_count:
                    final_text = curr_responses[-1]
                    # 等待流式傳輸完成
                    time.sleep(2)
                    updated = _harvest_responses(target_page, provider)
                    if updated and updated[-1] == final_text:
                        break
                    elif updated:
                        final_text = updated[-1]

            if not final_text:
                return {"status": "FAIL", "error": "response_timeout"}

            return {
                "status": "PASS",
                "provider": f"{provider}-web",
                "reasoning": final_text,
            }
    except Exception as exc:
        return {"status": "FAIL", "error": str(exc)[:300]}
