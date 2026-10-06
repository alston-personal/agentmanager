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

# Isolate persistent-profile corruption from Chromium/Playwright compatibility.
echo "oracle_gui_browser_smoke_stage=EPHEMERAL_CDP_DIAG"
BROWSER="$(cat "$ROOT/browser-path")"
TMP_PROFILE="$(mktemp -d /tmp/agentos-gui-ephemeral-profile-XXXXXX)"
EPHEMERAL_LOG="$(mktemp /tmp/agentos-gui-ephemeral-XXXXXX.log)"
cleanup_ephemeral() {
  if [[ -n "${EPHEMERAL_PID:-}" ]]; then kill "$EPHEMERAL_PID" >/dev/null 2>&1 || true; fi
  rm -rf "$TMP_PROFILE" "$EPHEMERAL_LOG"
}
trap cleanup_ephemeral EXIT
DISPLAY=:99 "$BROWSER" \
  --user-data-dir="$TMP_PROFILE" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9223 \
  --no-first-run --no-default-browser-check --disable-dev-shm-usage \
  about:blank >"$EPHEMERAL_LOG" 2>&1 &
EPHEMERAL_PID=$!
for _ in $(seq 1 30); do
  if curl -fsS --max-time 1 http://127.0.0.1:9223/json/version >/dev/null 2>&1; then break; fi
  sleep 0.5
done
if curl -fsS --max-time 2 http://127.0.0.1:9223/json/version >/dev/null 2>&1; then
  echo "oracle_gui_browser_ephemeral_cdp_http=PASS"
  "$PY" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print("oracle_gui_browser_ephemeral_stage=CONNECT_CDP", flush=True)
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9223', timeout=10000)
    print("oracle_gui_browser_ephemeral_cdp_attach=PASS", flush=True)
PY
else
  echo "oracle_gui_browser_ephemeral_cdp_http=FAIL"
fi
