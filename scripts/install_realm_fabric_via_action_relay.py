#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
RUNTIME = Path('/home/ubuntu/.local/share/agentos/action-relay-runtime')
SPOOL = Path('/home/ubuntu/agent-data/runtime/action-relay')
OUT = ROOT / '.agentos/evidence/realm-fabric-install-current.json'
ACTION = 'agentos.realm-fabric.install_release'

source_commit = (os.environ.get('AGENTOS_REALM_FABRIC_SOURCE_COMMIT') or '').strip().lower()
if len(source_commit) != 40 or any(c not in '0123456789abcdef' for c in source_commit):
    raise SystemExit('AGENTOS_REALM_FABRIC_SOURCE_COMMIT must be a 40-hex commit')

sys.path.insert(0, str(ROOT))
from agentos_node.action_relay import ActionRelayClient

OUT.parent.mkdir(parents=True, exist_ok=True)
runtime_file = RUNTIME / 'agentos_node/action_relay.py'
deadline = time.time() + 240
while time.time() < deadline:
    try:
        if runtime_file.is_file() and ACTION in runtime_file.read_text(encoding='utf-8'):
            break
    except OSError:
        pass
    time.sleep(1)
else:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'runtime_ready', 'action': ACTION, 'source_commit': source_commit}, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(2)

client = ActionRelayClient(SPOOL)
payload = client.submit(ACTION, {'source_commit': source_commit})
cid = payload['capsule_id']
deadline = time.time() + 180
receipt = None
while time.time() < deadline:
    receipt = client.receipt(cid)
    if receipt is not None:
        break
    time.sleep(1)
if receipt is None:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'receipt_timeout', 'capsule_id': cid, 'action': ACTION, 'source_commit': source_commit}, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(3)

OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(OUT.read_text(encoding='utf-8'))
if receipt.get('executor_user') != 'ubuntu':
    raise SystemExit(4)
if receipt.get('action') != ACTION or receipt.get('ok') is not True:
    raise SystemExit(5)
if receipt.get('source_commit') != source_commit:
    raise SystemExit(6)
raise SystemExit(0)
