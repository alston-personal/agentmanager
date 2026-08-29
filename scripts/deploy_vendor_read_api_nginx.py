#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path('/etc/nginx/sites-available/studio.milkcat.org')
MARKER_BEGIN = '# BEGIN milkcat vendor reputation read api'
MARKER_END = '# END milkcat vendor reputation read api'
PUBLIC_BASE = 'https://studio.milkcat.org/api/vendor-reputation/v1'
LOCAL_STATUS = 'http://127.0.0.1:18765/v1/status'

BLOCK = r'''    # BEGIN milkcat vendor reputation read api
    location = /api/vendor-reputation/v1/status {
        limit_except GET HEAD { deny all; }
        proxy_pass http://127.0.0.1:18765/v1/status;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location = /api/vendor-reputation/v1/vendors {
        limit_except GET HEAD { deny all; }
        proxy_pass http://127.0.0.1:18765/v1/vendors;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location = /api/vendor-reputation/v1/search {
        limit_except GET HEAD { deny all; }
        proxy_pass http://127.0.0.1:18765/v1/search;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location ~ ^/api/vendor-reputation/v1/vendors/[0-9a-fA-F-]+$ {
        limit_except GET HEAD { deny all; }
        rewrite ^/api/vendor-reputation(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:18765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location ~ ^/api/vendor-reputation/v1/vendors/[0-9a-fA-F-]+/(evidence|reputation)$ {
        limit_except GET HEAD { deny all; }
        rewrite ^/api/vendor-reputation(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:18765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    # END milkcat vendor reputation read api'''


def run(args, check=True, timeout=30):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f'command failed rc={p.returncode} stderr_length={len(p.stderr or "")}')
    return p


def http_json(url, method='GET', data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            ctype = r.headers.get('content-type', '')
            parsed = json.loads(raw) if 'json' in ctype else None
            return r.status, ctype, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors='replace')
        ctype = e.headers.get('content-type', '')
        parsed = None
        if 'json' in ctype:
            try:
                parsed = json.loads(raw)
            except Exception:
                pass
        return e.code, ctype, parsed


def curl_json(url, *, resolve_local=False, method='GET', data=None):
    args = ['curl', '-ksS', '--max-time', '10', '-X', method]
    if resolve_local:
        args += ['--resolve', 'studio.milkcat.org:443:127.0.0.1']
    if data is not None:
        args += ['-H', 'Content-Type: application/json', '--data', json.dumps(data)]
    args += ['-w', '\n__STATUS__%{http_code}\n__CTYPE__%{content_type}\n', url]
    p = run(args, check=False, timeout=15)
    text = p.stdout
    status = None
    ctype = ''
    body = text
    if '\n__STATUS__' in text:
        body, tail = text.rsplit('\n__STATUS__', 1)
        status_text, _, ctype_tail = tail.partition('\n__CTYPE__')
        try:
            status = int(status_text.strip())
        except Exception:
            status = None
        ctype = ctype_tail.strip()
    parsed = None
    if 'json' in ctype:
        try:
            parsed = json.loads(body)
        except Exception:
            pass
    return status, ctype, parsed


def brace_delta(line: str) -> int:
    return line.count('{') - line.count('}')


def find_studio_server(lines):
    depth = 0
    server_start = None
    server_depth = None
    candidates = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        before = depth
        if server_start is None and stripped.startswith('server') and '{' in stripped:
            server_start = idx
            server_depth = before + line.count('{')
        depth += brace_delta(line)
        if server_start is not None and depth < server_depth:
            block = '\n'.join(lines[server_start:idx + 1])
            if 'server_name' in block and 'studio.milkcat.org' in block:
                is_https = ('listen 443' in block) or ('ssl_certificate' in block)
                candidates.append((server_start, idx, is_https))
            server_start = None
            server_depth = None

    https = [c for c in candidates if c[2]]
    if len(https) == 1:
        return https[0][0], https[0][1]
    if len(https) > 1:
        raise RuntimeError('multiple studio HTTPS server blocks found')
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1]
    raise RuntimeError('studio HTTPS server block not found')


def strip_existing_marker(text: str) -> str:
    if MARKER_BEGIN not in text:
        return text
    if MARKER_END not in text:
        raise RuntimeError('vendor marker begin exists without end')
    before, rest = text.split(MARKER_BEGIN, 1)
    _, after = rest.split(MARKER_END, 1)
    return before.rstrip() + '\n' + after.lstrip('\n')


def require_json_probe(url, *, resolve_local=False, attempts=1):
    last = (None, '', None)
    for i in range(attempts):
        probe_url = url
        if not resolve_local:
            sep = '&' if '?' in url else '?'
            probe_url = f'{url}{sep}_probe={int(time.time() * 1000)}-{i}'
        last = curl_json(probe_url, resolve_local=resolve_local)
        if last[0] == 200 and 'json' in last[1] and isinstance(last[2], dict):
            return last
        time.sleep(1)
    return last


def main():
    if not CONFIG.is_file():
        raise RuntimeError('studio nginx config missing')

    local_code, _, local = http_json(LOCAL_STATUS)
    if local_code != 200 or not isinstance(local, dict):
        raise RuntimeError('local vendor status unavailable')
    evidence_before = int(local.get('evidence', -1))

    original = CONFIG.read_text()
    clean = strip_existing_marker(original)
    lines = clean.splitlines()
    _, server_end = find_studio_server(lines)
    lines.insert(server_end, BLOCK)
    updated = '\n'.join(lines) + ('\n' if clean.endswith('\n') else '')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = CONFIG.with_name(CONFIG.name + f'.vendor-read-api.{stamp}.bak')
    shutil.copy2(CONFIG, backup)

    changed = updated != original
    try:
        if changed:
            CONFIG.write_text(updated)
        run(['nginx', '-t'])
        if changed:
            run(['systemctl', 'reload', 'nginx'])
            time.sleep(1)

        local_status_code, local_status_type, local_public_status = require_json_probe(
            PUBLIC_BASE + '/status', resolve_local=True, attempts=2)
        local_vendors_code, local_vendors_type, local_public_vendors = require_json_probe(
            PUBLIC_BASE + '/vendors?limit=1', resolve_local=True, attempts=2)
        local_search_code, _, _ = curl_json(
            PUBLIC_BASE + '/search?q=test', resolve_local=True)

        if local_status_code != 200 or 'json' not in local_status_type or not isinstance(local_public_status, dict):
            raise RuntimeError('local nginx status acceptance failed')
        if local_vendors_code != 200 or 'json' not in local_vendors_type or not isinstance(local_public_vendors, dict):
            raise RuntimeError('local nginx vendors acceptance failed')
        if local_search_code != 200:
            raise RuntimeError('local nginx search acceptance failed')

        public_status_code, public_status_type, public_status = require_json_probe(
            PUBLIC_BASE + '/status', attempts=5)
        public_vendors_code, public_vendors_type, public_vendors = require_json_probe(
            PUBLIC_BASE + '/vendors?limit=1', attempts=5)
        public_search_code, _, _ = curl_json(
            PUBLIC_BASE + f'/search?q=test&_probe={int(time.time() * 1000)}')

        post_code, _, _ = curl_json(PUBLIC_BASE + '/evidence', method='POST', data={
            'source_type': 'boundary_test',
            'source_url': 'https://example.invalid/vendor-boundary-test'
        })
        local_code_after, _, local_after = http_json(LOCAL_STATUS)
        evidence_after = int(local_after.get('evidence', -2)) if isinstance(local_after, dict) else -2

        if public_status_code != 200 or 'json' not in public_status_type or not isinstance(public_status, dict):
            raise RuntimeError('public status acceptance failed')
        if public_vendors_code != 200 or 'json' not in public_vendors_type or not isinstance(public_vendors, dict):
            raise RuntimeError('public vendors acceptance failed')
        if public_search_code != 200:
            raise RuntimeError('public search acceptance failed')
        if post_code is None or 200 <= post_code < 400:
            raise RuntimeError('public write route unexpectedly accepted request')
        if local_code_after != 200 or evidence_before != evidence_after:
            raise RuntimeError('evidence count changed during write-boundary test')

        result = {
            'schema': 'milkcat.vendor-read-api-nginx-deploy/v1',
            'changed': changed,
            'nginx_test': 'pass',
            'reloaded': changed,
            'local_nginx_status': local_status_code,
            'local_nginx_vendors': local_vendors_code,
            'local_nginx_search': local_search_code,
            'public_status': public_status_code,
            'public_vendors': public_vendors_code,
            'public_search': public_search_code,
            'public_write_attempt': post_code,
            'evidence_before': evidence_before,
            'evidence_after': evidence_after,
            'whitelist': [
                '/v1/status', '/v1/vendors', '/v1/search',
                '/v1/vendors/{uuid}', '/v1/vendors/{uuid}/evidence', '/v1/vendors/{uuid}/reputation'
            ],
            'backup_created': backup.name,
            'raw_data_emitted': False,
            'core_modified': False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        if changed:
            shutil.copy2(backup, CONFIG)
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        raise


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            'schema': 'milkcat.vendor-read-api-nginx-deploy/v1',
            'ok': False,
            'error_type': type(exc).__name__,
            'error_length': len(str(exc)),
            'rolled_back_on_failure': True,
            'raw_data_emitted': False,
            'core_modified': False,
        }, ensure_ascii=False, indent=2))
        raise
