#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_start=WRONG_USER" >&2
  exit 2
fi

PERSONA="${AGENTOS_DM_PERSONA:-mio}"
case "$PERSONA" in mio) CDP_BASE=http://127.0.0.1:9222 ;; oursong) CDP_BASE=http://127.0.0.1:9223 ;; *) echo "threads_web_dm_login_start=INVALID_PERSONA" >&2; exit 2 ;; esac
AGENTOS_WEB_DM_CDP_URL="$CDP_BASE" python3 - <<'PY'
import json
import urllib.parse
import urllib.request

import os
base=os.environ['AGENTOS_WEB_DM_CDP_URL']
with urllib.request.urlopen(base+'/json/version',timeout=3) as r:
    meta=json.load(r)
assert meta.get('webSocketDebuggerUrl')

# Starting the login handoff only needs a visible persistent-browser tab.
# Use Chrome's bounded HTTP CDP endpoint instead of attaching Playwright;
# this avoids leaving a driver process holding scheduler stdout/stderr.
url='https://www.threads.com/login'
req=urllib.request.Request(
    base+'/json/new?'+urllib.parse.quote(url,safe=''),
    method='PUT',
)
with urllib.request.urlopen(req,timeout=5) as r:
    target=json.load(r)
assert target.get('id')

print('threads_web_dm_login_start=PASS')
print('threads_web_dm_login_mode=oracle_gui_worker')
print('threads_web_dm_login_browser_persistent=true')
print('threads_web_dm_login_remote_view=localhost_only')
print('threads_web_dm_login_transport=cdp_http')
print('threads_web_dm_login_cdp_url='+base)
PY
