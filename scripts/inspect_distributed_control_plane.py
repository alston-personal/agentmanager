#!/usr/bin/env python3
"""Run on the service's runtime node; persist sanitized acceptance only."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe(url, token, *, kind):
    headers = {'Authorization': 'Bearer ' + token} if kind not in ('shell', 'companion', 'auth_session') else {}
    if kind == 'auth_session':
        # Local probe must mimic the public virtual host; the OAuth bridge
        # intentionally refuses arbitrary Host headers on 127.0.0.1.
        headers['Host'] = 'agentos.milkcat.org'
    data = b'{}' if kind == 'approval' else None
    if data is not None:
        headers['Content-Type'] = 'application/json'
    try:
        try:
            response = urlopen(Request(url, data=data, headers=headers), timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read().decode('utf-8')
            status = response.status
            if kind == 'shell':
                valid = (status == 200 and '以 Google 登入' in body
                         and 'window.prompt(' not in body and 'Node Map' not in body
                         and bool(token) and token not in body)
                details = {'public_signin_ui': '以 Google 登入' in body,
                           'operator_prompt_absent': 'window.prompt(' not in body,
                           'operator_dashboard_absent': 'Node Map' not in body,
                           'credential_absent': bool(token) and token not in body,
                           'noindex': 'noindex' in response.headers.get('X-Robots-Tag', '')}
                valid = valid and details['noindex']
            elif kind == 'companion':
                valid = status == 200 and 'Node Map' in body and bool(token) and token not in body
                details = {'legacy_operator_ui': 'Node Map' in body,
                           'credential_absent': bool(token) and token not in body}
            elif kind == 'auth_session':
                payload = json.loads(body)
                valid = (status == 200 and isinstance(payload.get('loggedIn'), bool)
                         and isinstance(payload.get('providers'), dict)
                         and payload['loggedIn'] is False)
                details = {'anonymous_session': payload.get('loggedIn') is False,
                           'providers_present': isinstance(payload.get('providers'), dict)}
            elif kind == 'nodes':
                payload = json.loads(body)
                valid = status == 200 and payload.get('schema') == 'agentos.node-map/v0.1'
                details = {'node_count': payload.get('node_count')}
            else:
                payload = json.loads(body)
                valid = status == 400 and payload.get('error') == 'code is required'
                details = {'empty_code_rejected': valid, 'real_enrollment_mutated': False}
            return {'ok': valid, 'status': status, **details}
    except URLError as exc:
        return {'ok': False, 'error': 'dns_error' if isinstance(exc.reason, socket.gaierror) else 'transport_error'}
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        return {'ok': False, 'error': type(exc).__name__}


def inspect(expected_sha, public_url):
    def command(*args):
        return subprocess.check_output(args, text=True).strip()
    service = 'agentos-control-plane.service'
    props = dict(line.split('=', 1) for line in command('systemctl', '--user', 'show', service,
                 '-p', 'MainPID', '-p', 'ActiveState', '-p', 'WorkingDirectory').splitlines())
    pid = int(props['MainPID'])
    cwd = Path(f'/proc/{pid}/cwd').resolve(strict=True)
    env = dict(item.split('=', 1) for item in Path(f'/proc/{pid}/environ').read_bytes().decode().split('\0') if '=' in item)
    token = env.get('AGENTOS_CONTROL_PLANE_TOKEN', '')
    port = int(env['AGENTOS_CONTROL_PLANE_PORT'])
    observed_sha = command('git', '-C', str(cwd), 'rev-parse', 'HEAD')
    clean = not command('git', '-C', str(cwd), 'status', '--porcelain', '--untracked-files=no')
    local_url = f'http://127.0.0.1:{port}'
    probes = {}
    for label, base in [('local', local_url), ('public', public_url.rstrip('/'))]:
        probes[label] = {kind: probe(base + path, token, kind=kind) for kind, path in
                         [('shell', '/'), ('companion', '/companion'),
                          ('auth_session', '/dashboard/api/auth/session'),
                          ('nodes', '/v1/nodes'), ('approval', '/v1/nodes/approve')]}
    source_match = observed_sha == expected_sha and clean and cwd == Path(props['WorkingDirectory']).resolve()
    healthy = props['ActiveState'] == 'active' and all(p['ok'] for group in probes.values() for p in group.values())
    return {'schema': 'agentos.execution-receipt/v1', 'project_id': 'agentos-core',
            'capability': 'agentos.control-plane.convergence.inspect',
            'status': 'completed', 'parity': 'matched' if source_match and healthy else ('mismatch' if not source_match else 'unavailable'),
            'expected': {'source_sha': expected_sha},
            'observed': {'git_sha': observed_sha, 'release_path': str(cwd), 'source_match': source_match,
                         'service_active': props['ActiveState'] == 'active', **probes},
            'authority': {'kind': 'runtime_node', 'hostname': socket.gethostname(), 'sandbox_fallback_allowed': False},
            'checked_at': datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--public-url', default='https://agentos.milkcat.org')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        receipt = inspect(args.source_sha, args.public_url)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        receipt = {'schema': 'agentos.execution-receipt/v1', 'project_id': 'agentos-core',
                   'status': 'completed', 'parity': 'unavailable',
                   'expected': {'source_sha': args.source_sha},
                   'observed': {'error': 'service_inspection_failed', 'error_type': type(exc).__name__},
                   'authority': {'kind': 'runtime_node', 'hostname': socket.gethostname(),
                                 'sandbox_fallback_allowed': False},
                   'checked_at': datetime.now(timezone.utc).isoformat()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['parity'] == 'matched' else 1


if __name__ == '__main__':
    raise SystemExit(main())
