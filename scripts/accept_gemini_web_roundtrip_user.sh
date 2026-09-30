#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_roundtrip_acceptance=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"

"$PY" - <<'PY'
from __future__ import annotations
import time
from playwright.sync_api import sync_playwright

CDP='http://127.0.0.1:9222'
PROMPT='AgentOS Gemini bridge smoke test. Reply with exactly: AGENTOS_GEMINI_BRIDGE_OK'
MARKER='AGENTOS_GEMINI_BRIDGE_OK'

composer_selectors=[
    'rich-textarea div[contenteditable="true"]',
    'textarea[aria-label*="prompt" i]',
    '[contenteditable="true"][aria-label*="prompt" i]',
    'div.ql-editor[contenteditable="true"]',
    'textarea',
    '[contenteditable="true"]',
]

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

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp(CDP)
    if not browser.contexts:
        raise RuntimeError('gemini_roundtrip_no_browser_context')
    ctx=browser.contexts[0]
    pages=[x for x in ctx.pages if 'gemini.google.com' in str(x.url or '')]
    if not pages:
        raise RuntimeError('gemini_roundtrip_no_gemini_page')
    page=next((x for x in pages if first_visible(x,composer_selectors) is not None),pages[0])
    page.bring_to_front()
    composer=first_visible(page,composer_selectors)
    if composer is None:
        raise RuntimeError('gemini_roundtrip_composer_not_found')

    try:
        composer.fill(PROMPT)
    except Exception:
        composer.click()
        page.keyboard.press('ControlOrMeta+A')
        page.keyboard.type(PROMPT)

    print('gemini_web_roundtrip_inject=PASS')
    page.keyboard.press('Enter')
    print('gemini_web_roundtrip_submit=PASS')

    deadline=time.monotonic()+90
    seen=False
    while time.monotonic()<deadline:
        try:
            body=page.locator('body').inner_text(timeout=1500)
        except Exception:
            body=''
        # Require two occurrences: one in our prompt and one in Gemini's response.
        if body.count(MARKER) >= 2:
            seen=True
            break
        time.sleep(1)

    if not seen:
        raise TimeoutError('gemini_roundtrip_response_timeout')

    responses=[]
    for selector in ('model-response','[data-test-id*="model-response"]','.model-response-text','message-content'):
        try:
            loc=page.locator(selector)
            for i in range(max(0,loc.count()-6),loc.count()):
                try:
                    value=loc.nth(i).inner_text(timeout=1000).strip()
                except Exception:
                    continue
                if value:
                    responses.append(value)
        except Exception:
            pass
    if responses and not any(MARKER in x for x in responses):
        raise RuntimeError('gemini_roundtrip_marker_not_in_model_response')

    print('gemini_web_roundtrip_response=PASS')
    print('gemini_web_roundtrip_harvest=PASS')
    print('gemini_web_roundtrip_marker='+MARKER)
    print('gemini_web_roundtrip_acceptance=PASS')
PY
