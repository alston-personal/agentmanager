#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "oracle_gui_browser_smoke=WRONG_USER" >&2
  exit 2
fi

ROOT="$HOME/.local/share/agentos/gui-worker"
PY="$ROOT/venv/bin/python"
test -x "$PY"

echo "oracle_gui_browser_smoke_stage=CDP_HTTP_PREFLIGHT"
if ! curl -fsS --max-time 3 http://127.0.0.1:9222/json/version > /tmp/agentos-gui-cdp-version.json; then
  echo "oracle_gui_browser_smoke=CDP_HTTP_UNAVAILABLE"
  exit 3
fi
echo "oracle_gui_browser_cdp_http=PASS"

"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
print("oracle_gui_browser_smoke_stage=PLAYWRIGHT_START", flush=True)
with sync_playwright() as p:
    print("oracle_gui_browser_smoke_stage=CONNECT_CDP", flush=True)
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=10000)
    print("oracle_gui_browser_cdp_attach=PASS", flush=True)
    contexts=browser.contexts
    assert contexts
    ctx=contexts[0]
    page=ctx.pages[0] if ctx.pages else ctx.new_page()
    print("oracle_gui_browser_smoke_stage=NAVIGATE", flush=True)
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
