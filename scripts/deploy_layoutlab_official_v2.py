#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

CHECKOUT = Path(__file__).resolve().parents[1]
LIVE_REPO = Path('/home/ubuntu/agentmanager')
DATA = Path('/home/ubuntu/agent-data')
LAYOUTLIB = Path('/home/agentos-node/projects/layoutlib')
ANTIGRAVITY_RUNTIME = Path('/home/ubuntu/.local/share/agentos/runtime-vnext')
ANTIGRAVITY_RELAY = DATA / 'runtime/antigravity-relay'
EVIDENCE = CHECKOUT / '.agentos/evidence/layoutlab-official-v2.txt'
BASE_URL = 'https://studio.milkcat.org/layout-lab/'


def run(argv: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(argv, cwd=str(cwd or CHECKOUT), text=True, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(argv)}\nstdout={p.stdout[-12000:]}\nstderr={p.stderr[-12000:]}")
    return p


def curl(url: str, *, output: Path) -> int:
    p = run([
        'curl','-sS','-o',str(output),'-w','%{http_code}',
        '--retry','5','--retry-all-errors','--connect-timeout','5','--max-time','30',url
    ])
    return int(p.stdout.strip())


def allocate_port() -> int:
    env = dict(os.environ, AGENT_DATA_ROOT=str(DATA))
    subprocess.run([
        sys.executable, 'scripts/core_services/port_manager.py', 'allocate', 'layoutlab-api',
        '--desc', 'Layout Lab official-site API', '--start', '8800', '--end', '8899'
    ], cwd=str(CHECKOUT), env=env, text=True, check=True)
    p = subprocess.run([
        sys.executable, 'scripts/core_services/port_manager.py', 'list', '--json'
    ], cwd=str(CHECKOUT), env=env, text=True, capture_output=True, check=True)
    registry = json.loads(p.stdout)
    ports = sorted(int(port) for port, meta in registry.items() if meta.get('project') == 'layoutlab-api')
    if not ports:
        raise RuntimeError('Port Manager did not return a layoutlab-api allocation')
    return ports[0]


def submit_executor(port: int) -> tuple[str, Path]:
    sys.path.insert(0, str(ANTIGRAVITY_RUNTIME))
    from agentos_node.antigravity_relay import AntigravityRelayClient

    instruction = f'''Finish the Layout Lab official-site deployment on this Oracle host. You are authorized to make only the minimal changes required for Layout Lab and must preserve all unrelated routes and services.

Verified inputs:
- official URL: https://studio.milkcat.org/layout-lab/
- website repo: /home/ubuntu/zeus-writer
- website package: /home/ubuntu/zeus-writer/website
- expected static artifact: /home/ubuntu/zeus-writer/website/dist/layout-lab/index.html
- API source: /home/ubuntu/agentmanager/scripts/layoutlab_api.py
- LayoutLib root: /home/agentos-node/projects/layoutlib
- governed API port: {port}
- canonical API service name: layoutlab-api.service

Perform the deployment, not just an explanation:
1. First sync /home/ubuntu/agentmanager to canonical origin/main safely with git fetch + ff-only merge so scripts/layoutlab_api.py is current. Refuse destructive reset if dirty work would be lost.
2. Inspect the ACTUAL current HTTP server / reverse-proxy configuration serving studio.milkcat.org. Preserve unrelated configuration and routes.
3. Sync /home/ubuntu/zeus-writer safely: refuse destructive reset of user work. If clean, fetch and fast-forward the intended branch, then run the existing website build. Verify dist/layout-lab/index.html exists. If already current, do not rewrite unrelated source.
4. Create/update an ubuntu user systemd unit layoutlab-api.service that runs:
   /usr/bin/python3 /home/ubuntu/agentmanager/scripts/layoutlab_api.py --host 127.0.0.1 --port {port}
   with LAYOUTLIB_ROOT=/home/agentos-node/projects/layoutlib and PYTHONPATH as needed, Restart=on-failure. Use ubuntu's existing user manager (/run/user/1001/bus) if environment variables are needed.
5. Enable/restart that unit and prove GET http://127.0.0.1:{port}/healthz returns HTTP 200 JSON ok=true.
6. Add ONLY the minimal same-origin reverse-proxy mapping required so /layout-lab/api/ reaches 127.0.0.1:{port}, while /layout-lab/ continues serving the static page. Handle path stripping/preservation consistently with layoutlab_api.py, which accepts both /healthz,/parse and /layout-lab/api/healthz,/layout-lab/api/parse.
7. Before any web-server reload, back up only the config file(s) you modify and run the server's native config validation. If validation fails, restore and do not reload.
8. Reload only the affected existing HTTP server through the host's already configured privilege mechanism. Do not alter DNS, TLS certificates, firewall, unrelated vhosts, or unrelated applications.
9. Verify publicly from the host: UI HTTP 200, API health HTTP 200 JSON ok=true.
10. Create a small synthetic PNG floor plan and POST it as browser-equivalent multipart/form-data to https://studio.milkcat.org/layout-lab/api/parse with meters_per_pixel=0.02, wall_height_m=2.7, threshold=128, min_wall_length_px=16. Require HTTP 200, ok=true, Spatial IR, and at least one wall.
11. Return exact changed paths, unit state, web-server config validation/reload result, public status codes, parse wall count, and any caveat. Do not claim PASS unless actually verified.'''

    client = AntigravityRelayClient(ANTIGRAVITY_RELAY)
    capsule = client.submit(
        project_id='layoutlib',
        canonical_ir={
            'goal': 'Make LayoutLib directly usable at the stable official Studio URL.',
            'acceptance': [
                'https://studio.milkcat.org/layout-lab/ HTTP 200',
                'https://studio.milkcat.org/layout-lab/api/healthz HTTP 200 JSON ok=true',
                'browser-equivalent PNG multipart parse HTTP 200 with Spatial IR and walls > 0',
            ],
            'constraints': [
                'Preserve unrelated website routes and services',
                'Use governed localhost API port',
                'No DNS/TLS/firewall changes',
                'No destructive reset of existing user work',
            ],
        },
        instruction=instruction,
        workspace=str(LIVE_REPO),
    )
    cid = capsule['capsule_id']
    return cid, ANTIGRAVITY_RELAY / 'receipts' / f'{cid}.json'


def wait_receipt(path: Path, timeout: int = 480) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        time.sleep(1)
    raise TimeoutError(f'Antigravity receipt timeout: {path.name}')


def verify_public() -> dict:
    ui = Path('/tmp/layoutlab-v2-ui')
    health = Path('/tmp/layoutlab-v2-health')
    parse_out = Path('/tmp/layoutlab-v2-parse')
    fixture = Path('/tmp/layoutlab-v2-fixture.png')

    ui_code = curl(BASE_URL, output=ui)
    if ui_code != 200 or 'Layout Lab' not in ui.read_text(errors='replace'):
        raise RuntimeError(f'official UI acceptance failed: HTTP {ui_code}')

    health_code = curl(BASE_URL + 'api/healthz', output=health)
    health_json = json.loads(health.read_text()) if health.exists() else {}
    if health_code != 200 or health_json.get('ok') is not True:
        raise RuntimeError(f'official health acceptance failed: HTTP {health_code}, payload={health_json}')

    from PIL import Image, ImageDraw
    im = Image.new('L', (320, 240), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((30, 30, 290, 210), outline=0, width=10)
    im.save(fixture)

    p = run([
        'curl','-sS','-o',str(parse_out),'-w','%{http_code}',
        '--retry','3','--retry-all-errors','--connect-timeout','5','--max-time','40',
        '-F',f'image=@{fixture}',
        '-F','meters_per_pixel=0.02',
        '-F','wall_height_m=2.7',
        '-F','threshold=128',
        '-F','min_wall_length_px=16',
        BASE_URL + 'api/parse',
    ])
    parse_code = int(p.stdout.strip())
    parse_json = json.loads(parse_out.read_text()) if parse_out.exists() else {}
    ir = parse_json.get('ir') or {}
    walls = ir.get('walls') or []
    if parse_code != 200 or parse_json.get('ok') is not True or not walls:
        raise RuntimeError(f'official parse acceptance failed: HTTP {parse_code}, payload={json.dumps(parse_json)[:4000]}')
    return {
        'ui_http': ui_code,
        'health_http': health_code,
        'parse_http': parse_code,
        'wall_count': len(walls),
        'spatial_ir_version': ir.get('version'),
    }


def main() -> int:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    try:
        run([sys.executable, 'scripts/bootstrap_layoutlib.py', '--target', str(LAYOUTLIB)])
        run([sys.executable, 'scripts/bootstrap_layoutlib_hardening.py', '--target', str(LAYOUTLIB)])
        port = allocate_port()
        lines.append(f'governed_port={port}')
        cid, receipt_path = submit_executor(port)
        lines.append(f'capsule_id={cid}')
        receipt = wait_receipt(receipt_path)
        lines.append('=== EXECUTOR RECEIPT ===')
        lines.append(json.dumps(receipt, ensure_ascii=False, indent=2))
        if receipt.get('ok') is not True:
            raise RuntimeError('Antigravity deployment receipt is not ok=true')
        acceptance = verify_public()
        lines.append('=== INDEPENDENT ACCEPTANCE ===')
        for key, value in acceptance.items():
            lines.append(f'{key}={value}')
        lines.append('official_url=https://studio.milkcat.org/layout-lab/')
        lines.append('official_layoutlab_goal=PASS')
        EVIDENCE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print('\n'.join(lines[-8:]))
        return 0
    except Exception as exc:
        lines.append(f'official_layoutlab_goal=FAIL error={type(exc).__name__}: {exc}')
        EVIDENCE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(lines[-1], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
