#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_session_acceptance=WRONG_USER" >&2
  exit 2
fi

export PYTHONPATH="${AGENTOS_REPO:-$HOME/agentmanager}"
export AGENTOS_GEMINI_WEB_BRIDGE="$HOME/.local/share/agentos/gemini-web/bridge"

python3 - <<'PY'
import time
from agentos_node.session_bridge import FileSessionBridge

bridge=FileSessionBridge.from_environment('gemini-web')
index=bridge.discover()
sessions=index.get('sessions') or []
assert sessions,index
session=next((s for s in sessions if s.get('state')=='READY'),None)
if session is None:
    login=next((s for s in sessions if s.get('state')=='LOGIN_REQUIRED'),None)
    if login:
        print('gemini_web_session_acceptance=LOGIN_REQUIRED')
        print('gemini_web_handoff_required=true')
        raise SystemExit(20)
    raise AssertionError(sessions)
sid=session['session_id']
print('gemini_web_discover=PASS')
print('gemini_web_session_id='+sid)

def request(op,payload=None):
    req=bridge.request(op,session_id=sid,payload=payload or {})
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        receipt=bridge.receipt(req['request_id'])
        if receipt is not None:
            assert receipt.get('provider')=='gemini-web',receipt
            return receipt
        time.sleep(.25)
    raise TimeoutError(op)

attach=request('attach')
assert attach.get('ok') is True,attach
print('gemini_web_attach=PASS')

inspect=request('snapshot')
assert inspect.get('ok') is True,inspect
assert (inspect.get('output') or {}).get('state')=='READY',inspect
print('gemini_web_inspect=PASS')

marker='AgentOS Gemini bridge acceptance context — draft only, do not submit.'
inject=request('inject',{'text':marker,'submit':False})
assert inject.get('ok') is True,inject
assert (inject.get('output') or {}).get('draft_prepared') is True,inject
assert (inject.get('output') or {}).get('submitted') is False,inject
print('gemini_web_inject_draft=PASS')

clear=request('inject',{'text':'','submit':False})
assert clear.get('ok') is True,clear
print('gemini_web_inject_cleanup=PASS')
print('gemini_web_receipt=PASS')
print('gemini_web_session_acceptance=PASS')
PY
