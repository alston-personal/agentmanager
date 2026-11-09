#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != "ubuntu" ]; then
  echo "chatgpt_web_session_acceptance=WRONG_USER" >&2
  exit 2
fi

export PYTHONPATH="${AGENTOS_REPO:-$HOME/agentmanager}"
export AGENTOS_CHATGPT_WEB_BRIDGE="$HOME/.local/share/agentos/chatgpt-web/bridge"

python3 - <<'PY'
import time
from agentos_node.session_bridge import FileSessionBridge

bridge=FileSessionBridge.from_environment('chatgpt-web')
index=bridge.discover()
sessions=index.get('sessions') or []
assert sessions,index
session=next((s for s in sessions if s.get('state')=='READY'),None)
assert session, sessions
sid=session['session_id']
print('chatgpt_web_discover=PASS')
print('chatgpt_web_session_id='+sid)

def request(op,payload=None):
    req=bridge.request(op,session_id=sid,payload=payload or {})
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        receipt=bridge.receipt(req['request_id'])
        if receipt is not None:
            assert receipt.get('provider')=='chatgpt-web',receipt
            return receipt
        time.sleep(.25)
    raise TimeoutError(op)

attach=request('attach')
assert attach.get('ok') is True,attach
print('chatgpt_web_attach=PASS')

inspect=request('snapshot')
assert inspect.get('ok') is True,inspect
assert (inspect.get('output') or {}).get('state')=='READY',inspect
print('chatgpt_web_inspect=PASS')

marker='AgentOS bridge acceptance context — draft only, do not submit.'
inject=request('inject',{'text':marker,'submit':False})
assert inject.get('ok') is True,inject
assert (inject.get('output') or {}).get('draft_prepared') is True,inject
assert (inject.get('output') or {}).get('submitted') is False,inject
print('chatgpt_web_inject_draft=PASS')

clear=request('inject',{'text':'','submit':False})
assert clear.get('ok') is True,clear
print('chatgpt_web_inject_cleanup=PASS')
print('chatgpt_web_receipt=PASS')
print('chatgpt_web_session_acceptance=PASS')
PY
