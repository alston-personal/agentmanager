#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

RUNTIME = Path('/home/ubuntu/.local/share/agentos/runtime-vnext')
RELAY = Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
EVIDENCE = Path('.agentos/evidence/studio-web-migration-audit.txt')

sys.path.insert(0, str(RUNTIME))
from agentos_node.antigravity_relay import AntigravityRelayClient

INSTRUCTION = r'''Audit the COMPLETE current production surface of https://studio.milkcat.org before any repository extraction or migration. This is NOT only a Zeus Writer migration. The official site has accumulated multiple services, product pages, reverse proxies, APIs, static applications, deployment workflows, background services and ports. We need a safe plan to extract the platform website from /home/ubuntu/zeus-writer/website into an independent studio-web project without breaking anything.

Do a read-only production audit. Do NOT change web server config, DNS, TLS, services, repositories, ports, running processes, or deployed files.

Required audit:
1. Identify the actual source checkout(s), build output(s), and deployment path(s) used by studio.milkcat.org. Include /home/ubuntu/zeus-writer/website but do not assume it is the only source.
2. Inspect the active web server configuration for studio.milkcat.org and enumerate every location/route, static root/alias, reverse proxy, upstream, websocket/SSE rule, SPA fallback, redirect and special header that affects the domain.
3. Enumerate every product/service currently integrated into the official site, including but not limited to Zeus Writer and Layout Lab. For each item record: public route, owning source repo/path, build command/output, backend/API dependency, localhost port, service/process name, persistence mechanism, config/env dependencies, and whether it is tightly coupled to the current website tree.
4. Inspect relevant user/system services, safe persistent-process conventions, governed port registry, running listeners, containers if relevant, and AgentOS-managed services. Correlate each backend with the public route that reaches it.
5. Inspect GitHub Actions/deployment scripts in /home/ubuntu/agentmanager and any local repository workflows that can mutate studio.milkcat.org. List all workflows that must be updated when the website is extracted.
6. Inspect the current website source for cross-directory imports/references to parent Zeus Writer files, shared assets, node packages, generated artifacts, symlinks, env files, absolute paths, and assumptions that would break when moved to /home/ubuntu/studio-web.
7. Establish a production baseline test matrix BEFORE migration. At minimum test every discovered public route plus important API health endpoints and at least one representative functional request for every interactive backend. Record HTTP status, content marker, API response shape, and where appropriate POST/functionality checks. Do not mutate user data.
8. Identify routes that cannot be safely probed without mutation and state the safe substitute check.
9. Produce a dependency graph and migration risk classification (low/medium/high) for every integrated service.
10. Design a staged migration with no destructive cutover: create independent studio-web checkout/repo, reproduce build in parallel, run an alternate local/staging origin, compare baseline, switch only the document root/integration references needed, validate all routes, and retain a fast rollback to the old tree until acceptance passes.
11. Define explicit GO/NO-GO acceptance gates and rollback triggers. A migration must be NO-GO if any existing route, API, asset path, auth flow, websocket/SSE flow, or representative functional test regresses.
12. Recommend what belongs in studio-web versus what remains in product repositories. studio-web should own platform shell/navigation/integration contracts; product logic should remain in product repos unless there is concrete evidence otherwise.
13. Return exact discovered paths/config files/service names/ports/routes/workflows, baseline results, dependency findings, migration phases, rollback procedure, and unresolved unknowns.

Important: Do not invent services. Derive the inventory from the actual host, active config, repositories and running system. The goal is zero-regression extraction of the full studio.milkcat.org platform, not merely moving a folder.'''

CANONICAL_IR = {
    'goal': 'Safely extract the complete studio.milkcat.org platform website into an independent studio-web project with zero regression across all integrated services.',
    'acceptance': [
        'Complete production route/service/workflow inventory from actual host state',
        'Pre-migration baseline for every discovered public integration',
        'Dependency graph and risk classification',
        'Staged parallel migration plan with explicit rollback and GO/NO-GO gates',
    ],
    'constraints': [
        'Audit phase is read-only',
        'Do not treat Zeus Writer as the only integrated service',
        'No DNS/TLS/firewall/web-server/service/repository mutation during audit',
        'Preserve all existing routes and behavior in later migration',
    ],
}


def main() -> int:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    client = AntigravityRelayClient(str(RELAY))
    submission = client.submit(
        project_id='studio-web-migration',
        canonical_ir=CANONICAL_IR,
        instruction=INSTRUCTION,
        workspace='/home/ubuntu/agentmanager',
    )
    capsule_id = submission['capsule_id']
    receipt_path = RELAY / 'receipts' / f'{capsule_id}.json'
    print(f'capsule_id={capsule_id}', flush=True)

    deadline = time.time() + 600
    while time.time() < deadline and not receipt_path.exists():
        time.sleep(1)
    if not receipt_path.exists():
        raise RuntimeError(f'receipt timeout: {capsule_id}')

    receipt = json.loads(receipt_path.read_text())
    EVIDENCE.write_text(
        f'capsule_id={capsule_id}\n' + json.dumps(receipt, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    if receipt.get('ok') is not True:
        raise RuntimeError(f'AgentOS audit failed: {receipt}')

    text = (receipt.get('stdout', '') + '\n' + receipt.get('stderr', '')).lower()
    required = ['studio.milkcat.org', 'route', 'rollback', 'baseline']
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError('audit receipt lacks required evidence: ' + ','.join(missing))

    print('studio_web_migration_audit_receipt=PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
