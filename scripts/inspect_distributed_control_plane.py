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
from urllib.parse import urlsplit, parse_qs
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.request import Request, urlopen


def probe(url, token, *, kind):
    headers = {'Authorization': 'Bearer ' + token} if kind not in ('shell', 'welcome', 'companion', 'auth_session', 'account_anon', 'virtual_one_anon', 'my_one_anon', 'platform_anon', 'platform_page_anon') else {}
    if kind in ('auth_session', 'account_anon', 'virtual_one_anon', 'my_one_anon', 'platform_anon', 'platform_page_anon'):
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
            elif kind == 'welcome':
                # Check the current public UI contract, not stale page copy.
                # Source/live mismatch must fail, while anonymous admin APIs
                # continue to be checked separately by platform_anon probes.
                details = {
                    'session_status_ui': '登入狀態' in body,
                    'account_header': 'id="agentos-account-identity"' in body,
                    'account_from_session': 'session.username' in body and 'session.role' in body,
                    'admin_navigation': 'id="platform-admin-link"' in body,
                    'onboarding_request_ui': 'id="create-realm"' in body,
                    'onboarding_route': '/v1/account/realm-request' in body,
                    'account_switch': '/dashboard/api/auth/logout?returnTo=%2F' in body,
                    'obsolete_copy_absent': '管理者 Console 不會自動開放' not in body,
                    'credential_absent': bool(token) and token not in body,
                }
                valid = status == 200 and all(details.values())
            elif kind == 'companion':
                valid = status == 200 and 'Node Map' in body and bool(token) and token not in body
                details = {'legacy_operator_ui': 'Node Map' in body,
                           'credential_absent': bool(token) and token not in body}
            elif kind in ('account_anon', 'virtual_one_anon', 'my_one_anon'):
                payload = json.loads(body)
                valid = status == 401 and payload.get('error') == 'signin_required'
                details = {'anonymous_denied': valid}
            elif kind == 'platform_page_anon':
                # A protected HTML page may explain the missing credential,
                # but it must never expose a review queue to the visitor.
                valid = (status == 401 and '平台管理者帳號登入' in body
                         and 'returnTo=%2Fplatform' in body
                         and '待審申請：' not in body
                         and '核准申請（不代表開通）' not in body)
                details = {'unauthorized_platform_denied': status == 401,
                           'actionable_login_ui': 'returnTo=%2Fplatform' in body,
                           'protected_review_absent': '核准（待 ONE 開通）' not in body}
            elif kind == 'platform_anon':
                payload = json.loads(body)
                valid = status == 401 and payload.get('error') == 'signin_required'
                details = {'unauthorized_platform_denied': valid}
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



class _NeverFollowProviderRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_oauth_origin(base, provider, *, local):
    """Inspect only OAuth callback origin and state; never log provider URLs."""
    if provider not in {'google', 'github', 'facebook', 'line'}:
        raise ValueError('unknown OAuth provider')
    uri = base.rstrip('/') + '/dashboard/api/auth/signin/' + provider + '?site=agentos&returnTo=%2F'
    headers = {'Host': 'agentos.milkcat.org'} if local else {}
    try:
        opener = build_opener(_NeverFollowProviderRedirect())
        try:
            response = opener.open(Request(uri, headers=headers), timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.status
            if status not in (302, 307):
                return {'ok': False, 'status': status, 'error': 'oauth_redirect_unavailable'}
            query = parse_qs(urlsplit(response.headers.get('Location', '')).query)
            expected = 'https://agentos.milkcat.org/dashboard/api/auth/callback/' + provider
            correct_callback = query.get('redirect_uri', [''])[0] == expected
            has_state = bool(query.get('state', [''])[0])
            return {'ok': correct_callback and has_state, 'status': status,
                    'agentos_callback': correct_callback, 'oauth_state_present': has_state}
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return {'ok': False, 'error': 'oauth_transport_error'}


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
                         [('shell', '/'), ('welcome', '/welcome'), ('companion', '/companion'),
                          ('auth_session', '/dashboard/api/auth/session'),
                          ('account_anon', '/v1/account/realm-request'),
                          ('virtual_one_anon', '/v1/account/virtual-one'),
                          ('my_one_anon', '/my-one'),
                          ('platform_anon', '/v1/platform/realm-requests'),
                          ('platform_page_anon', '/platform'),
                          ('nodes', '/v1/nodes'), ('approval', '/v1/nodes/approve')]}
        for provider in ('google', 'github', 'facebook', 'line'):
            probes[label]['oauth_' + provider] = probe_oauth_origin(base, provider, local=label == 'local')
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
