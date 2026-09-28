#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "oracle_gui_browser_smoke=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"

"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    contexts=browser.contexts
    assert contexts
    ctx=contexts[0]
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://example.com',wait_until='domcontentloaded',timeout=20000)
    title=page.title()
    url=page.url
    assert title=='Example Domain',title
    assert url.startswith('https://example.com'),url
    print('oracle_gui_browser_smoke=PASS')
    print('oracle_gui_browser_contexts='+str(len(contexts)))
    print('oracle_gui_browser_pages='+str(len(ctx.pages)))
    print('oracle_gui_browser_title='+title)
PY
