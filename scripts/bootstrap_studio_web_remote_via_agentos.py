#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

# When this file is executed as `python3 scripts/...py`, Python puts `scripts/`
# at sys.path[0]. This repo also has scripts/agentos_node.py, which would shadow
# the real AgentOS runtime package. Pin the canonical runtime ahead of it.
RUNTIME = '/home/ubuntu/.local/share/agentos/runtime-vnext'
if RUNTIME in sys.path:
    sys.path.remove(RUNTIME)
sys.path.insert(0, RUNTIME)

from agentos_node.antigravity_relay import AntigravityRelayClient

RELAY = Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
OUT = Path('.agentos/evidence/studio-web-remote-agentos.txt')

INSTRUCTION = '''Use the ubuntu execution identity on this Oracle host to bootstrap the independent GitHub remote for Studio Web.

Goal: create private repository alston-personal/studio-web if, and only if, the existing ubuntu GitHub credential is already authenticated and authorized to do so.

Rules:
1. First run a non-secret authentication check such as gh auth status. Never print or expose tokens, credentials, environment secrets, or config file contents containing secrets.
2. Check whether alston-personal/studio-web already exists. If it exists, do not recreate or alter settings; report it as existing.
3. If it does not exist and the current ubuntu GitHub identity is authorized, create it as a PRIVATE repository with a concise description indicating it owns the studio.milkcat.org platform web shell and website-owned integrations.
4. Do NOT modify nginx, DNS, TLS, any running service, any production website file, Zeus Writer, LayoutLib, or any other product repository.
5. Do NOT push source yet. This step establishes only the remote repository boundary.
6. Verify the repository can be viewed after creation and report the authenticated GitHub login if safe to show, whether the repo existed or was created, visibility, exact repo name, and any authorization failure.
7. If no authenticated/authorized ubuntu GitHub credential exists, make no changes and return a clear NO_GO reason.

This is a governed repository-boundary operation, not a production deployment.'''


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    client = AntigravityRelayClient(RELAY)
    capsule = client.submit(
        project_id='studio-web-migration',
        canonical_ir={
            'goal': 'Establish an independent private GitHub repository boundary for Studio Web without production changes.',
            'acceptance': [
                'alston-personal/studio-web exists',
                'repository visibility is private',
                'no production mutation',
            ],
            'constraints': [
                'never expose credentials',
                'no nginx/DNS/TLS/service/product-repo changes',
                'do not push source in this step',
            ],
        },
        instruction=INSTRUCTION,
        workspace='/home/ubuntu/agentmanager',
    )
    capsule_id = capsule['capsule_id']
    receipt_path = RELAY / 'receipts' / f'{capsule_id}.json'
    deadline = time.time() + 420
    while time.time() < deadline and not receipt_path.exists():
        time.sleep(1)
    lines = [f'capsule_id={capsule_id}']
    if not receipt_path.exists():
        lines.append('agentos_receipt=TIMEOUT')
        OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return 3
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    lines.append(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append('agentos_receipt_ok=' + str(bool(receipt.get('ok'))).lower())
    text = ((receipt.get('stdout') or '') + '\n' + (receipt.get('stderr') or '')).lower()
    if receipt.get('ok') is True and 'alston-personal/studio-web' in text:
        lines.append('studio_web_remote_agentos=PASS')
        rc = 0
    else:
        lines.append('studio_web_remote_agentos=NO_GO')
        rc = 4
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(OUT.read_text(encoding='utf-8'))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
