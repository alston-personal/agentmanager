#!/usr/bin/env python3
from __future__ import annotations
import json, sys, time
from pathlib import Path

ROOT = Path.cwd()
RUNTIME = Path('/home/ubuntu/.local/share/agentos/action-relay-runtime')
SPOOL = Path('/home/ubuntu/agent-data/runtime/action-relay')
OUT = ROOT / '.agentos/evidence/layoutlib-v079-import-action-relay.txt'
ACTION = 'github.repo.import_layoutlib_v079'
SOURCE_COMMIT = 'e8efc4ed7cbd41839f960373f79c5fb6a5f82375'
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
payload=client.submit(ACTION, {'repository': REPOSITORY, 'source_commit': SOURCE_COMMIT})
cid=payload['capsule_id']
lines.append('capsule_id='+cid)
deadline=time.time()+240
receipt=None
while time.time()<deadline:
    receipt=client.receipt(cid)
    if receipt is not None:
        break
    time.sleep(1)
if receipt is None:
    lines.append('action_receipt=TIMEOUT')
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    raise SystemExit(3)
lines.append(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True))

# Action Relay action receipts expose the action result fields at the top level.
# Keep backward compatibility with an older nested-result envelope if encountered.
result = receipt.get('result') if isinstance(receipt.get('result'), dict) else receipt
checks = {
    'receipt_ok': receipt.get('ok') is True,
    'repository': result.get('repository') == REPOSITORY,
    'source_commit': result.get('source_commit') == SOURCE_COMMIT,
    'release': result.get('release') == 'v0.7.9',
    'file_count': result.get('file_count') == 7,
    'target_commit': bool(result.get('target_commit')),
}
for key, ok in checks.items():
    lines.append(f'{key}=' + ('PASS' if ok else 'NO_GO'))
lines.append('executor_user='+str(receipt.get('executor_user')))
passed=all(checks.values())
lines.append('layoutlib_v079_import=' + ('PASS' if passed else 'NO_GO'))
OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(OUT.read_text(encoding='utf-8'))
raise SystemExit(0 if passed else 4)
