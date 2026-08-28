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
DEPLOYMENT_STATE = Path('/home/ubuntu/agent-data/governance/core-deployment.json')
OUT = ROOT / '.agentos/evidence/realm-fabric-install-current.json'
CLAIM_ACTION = 'agentos.realm-fabric.claim_deployment'
ADVANCE_ACTION = 'agentos.realm-fabric.advance_deployment'
INSTALL_ACTION = 'agentos.realm-fabric.install_release'
STATUS_ACTION = 'agentos.realm-fabric.deployment_status'

source_commit = (os.environ.get('AGENTOS_REALM_FABRIC_SOURCE_COMMIT') or '').strip().lower()
lease_owner = (os.environ.get('AGENTOS_REALM_FABRIC_LEASE_OWNER') or 'agentos-core-mainline').strip()
if len(source_commit) != 40 or any(c not in '0123456789abcdef' for c in source_commit):
    raise SystemExit('AGENTOS_REALM_FABRIC_SOURCE_COMMIT must be a 40-hex commit')
if not lease_owner:
    raise SystemExit('AGENTOS_REALM_FABRIC_LEASE_OWNER must be non-empty')

sys.path.insert(0, str(ROOT))
from agentos_node.action_relay import ActionRelayClient

OUT.parent.mkdir(parents=True, exist_ok=True)
runtime_file = RUNTIME / 'agentos_node/action_relay.py'
deadline = time.time() + 240
while time.time() < deadline:
    try:
        body = runtime_file.read_text(encoding='utf-8') if runtime_file.is_file() else ''
        if all(action in body for action in (CLAIM_ACTION, ADVANCE_ACTION, INSTALL_ACTION, STATUS_ACTION)) and 'realm_fabric_deployment_fence_v1' in body:
            break
    except OSError:
        pass
    time.sleep(1)
else:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'runtime_ready', 'source_commit': source_commit}, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(2)

client = ActionRelayClient(SPOOL)


def wait_receipt(capsule_id: str, timeout: int = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        receipt = client.receipt(capsule_id)
        if receipt is not None:
            return receipt
        time.sleep(1)
    raise TimeoutError(capsule_id)


def current_state() -> dict:
    try:
        data = json.loads(DEPLOYMENT_STATE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


state_before = current_state()
expected_generation = int(state_before.get('deployment_generation') or 0)
claim_payload = client.submit(CLAIM_ACTION, {
    'desired_core_commit': source_commit,
    'lease_owner': lease_owner,
    'expected_generation': expected_generation,
    'lease_seconds': 900,
})
try:
    claim = wait_receipt(claim_payload['capsule_id'])
except TimeoutError:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'claim_receipt_timeout'}, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(3)

advance = None
if claim.get('ok') is True:
    generation = int(claim.get('deployment_generation') or 0)
elif (
    claim.get('deployment_status') == 'rejected_lease'
    and claim.get('lease_owner') == lease_owner
    and claim.get('desired_core_commit')
    and claim.get('desired_core_commit') != source_commit
):
    advance_payload = client.submit(ADVANCE_ACTION, {
        'current_desired_core_commit': str(claim.get('desired_core_commit')),
        'next_desired_core_commit': source_commit,
        'lease_owner': lease_owner,
        'expected_generation': int(claim.get('deployment_generation') or expected_generation),
        'lease_seconds': 900,
    })
    try:
        advance = wait_receipt(advance_payload['capsule_id'])
    except TimeoutError:
        OUT.write_text(json.dumps({'ok': False, 'stage': 'advance_receipt_timeout', 'claim': claim}, indent=2) + '\n', encoding='utf-8')
        raise SystemExit(4)
    if advance.get('executor_user') != 'ubuntu' or advance.get('action') != ADVANCE_ACTION or advance.get('ok') is not True:
        OUT.write_text(json.dumps({'ok': False, 'stage': 'advance', 'claim': claim, 'advance': advance}, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(OUT.read_text(encoding='utf-8'))
        raise SystemExit(5)
    generation = int(advance.get('deployment_generation') or 0)
else:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'claim', 'claim': claim}, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(OUT.read_text(encoding='utf-8'))
    raise SystemExit(6)

if generation <= expected_generation:
    raise SystemExit('deployment generation did not advance')

install_payload = client.submit(INSTALL_ACTION, {
    'source_commit': source_commit,
    'desired_core_commit': source_commit,
    'lease_owner': lease_owner,
    'deployment_generation': generation,
})
try:
    receipt = wait_receipt(install_payload['capsule_id'])
except TimeoutError:
    OUT.write_text(json.dumps({'ok': False, 'stage': 'install_receipt_timeout', 'generation': generation}, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(7)

status_payload = client.submit(STATUS_ACTION, {})
try:
    status = wait_receipt(status_payload['capsule_id'], timeout=60)
except TimeoutError:
    status = {'ok': False, 'deployment_status': 'status_timeout'}

combined = dict(receipt)
combined['claim_receipt'] = claim
if advance is not None:
    combined['advance_receipt'] = advance
combined['deployment_status_receipt'] = status
OUT.write_text(json.dumps(combined, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(OUT.read_text(encoding='utf-8'))

if receipt.get('executor_user') != 'ubuntu':
    raise SystemExit(8)
if receipt.get('action') != INSTALL_ACTION or receipt.get('ok') is not True:
    raise SystemExit(9)
if receipt.get('source_commit') != source_commit:
    raise SystemExit(10)
if receipt.get('desired_core_commit') != source_commit:
    raise SystemExit(11)
if receipt.get('observed_core_commit') != source_commit:
    raise SystemExit(12)
if receipt.get('deployment_generation') != generation:
    raise SystemExit(13)
if receipt.get('lease_owner') != lease_owner:
    raise SystemExit(14)
if receipt.get('deployment_status') != 'converged':
    raise SystemExit(15)
if status.get('deployment_status') != 'converged':
    raise SystemExit(16)
if status.get('desired_core_commit') != source_commit or status.get('observed_core_commit') != source_commit:
    raise SystemExit(17)
raise SystemExit(0)
