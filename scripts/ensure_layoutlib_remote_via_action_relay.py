#!/usr/bin/env python3
from __future__ import annotations
import json, sys, time
from pathlib import Path

ROOT = Path.cwd()
RUNTIME = Path('/home/ubuntu/.local/share/agentos/action-runtime')
SPOOL = Path('/home/ubuntu/agent-data/runtime/action-relay')
OUT = ROOT / '.agentos/evidence/layoutlib-remote-action-relay.txt'
ACTION = 'github.repo.ensure_layoutlib'
REPOSITORY = 'alston-personal/layoutlib'

sys.path.insert(0, str(ROOT))
from agentos_node.action_relay import ActionRelayClient

OUT.parent.mkdir(parents=True, exist_ok=True)
lines=[]
deadline=time.time()+240
runtime_file=RUNTIME/'agentos_node/action_relay.py'
while time.time()<deadline:
    try:
        if runtime_file.is_file() and ACTION in runtime_file.read_text(encoding='utf-8'):
            lines.append('action_runtime_ready=PASS')
            break
    except OSError:
        pass
    time.sleep(1)
else:
    lines.append('action_runtime_ready=TIMEOUT')
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    raise SystemExit(2)

client=ActionRelayClient(SPOOL)
payload=client.submit(ACTION, {'repository': REPOSITORY})
cid=payload['capsule_id']
lines.append('capsule_id='+cid)
deadline=time.time()+120
receipt=None
while time.time()<deadline:
    receipt=client.receipt(cid)
    if receipt is not None: break
    time.sleep(1)
if receipt is None:
    lines.append('action_receipt=TIMEOUT')
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    raise SystemExit(3)
lines.append(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True))
lines.append('executor_user='+str(receipt.get('executor_user')))
lines.append('layoutlib_remote_action_relay=' + ('PASS' if receipt.get('ok') is True else 'NO_GO'))
OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(OUT.read_text(encoding='utf-8'))
raise SystemExit(0 if receipt.get('ok') is True else 4)
