#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import time
import urllib.error
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


def run(args, check=True):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
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


def brace_delta(line: str) -> int:
    # Nginx config here does not use braces inside quoted values in the target server block.
    return line.count('{') - line.count('}')


def find_studio_server(lines):
    depth = 0
    server_start = None
    server_depth = None
    has_domain = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        before = depth
        if server_start is None and stripped.startswith('server') and '{' in stripped:
            server_start = idx
            server_depth = before + line.count('{')
            has_domain = False
        if server_start is not None and 'server_name' in stripped and 'studio.milkcat.org' in stripped:
            has_domain = True
        depth += brace_delta(line)
        if server_start is not None and depth < server_depth:
            if has_domain:
                return server_start, idx
            server_start = None
            server_depth = None
            has_domain = False
    raise RuntimeError('studio.milkcat.org server block not found')


def strip_existing_marker(text: str) -> str:
    if MARKER_BEGIN not in text:
        return text
    if MARKER_END not in text:
        raise RuntimeError('vendor marker begin exists without end')
    before, rest = text.split(MARKER_BEGIN, 1)
    _, after = rest.split(MARKER_END, 1)
    # Remove the marker lines and their block while preserving surrounding content.
    return before.rstrip() + '\n' + after.lstrip('\n')


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

        status_code, status_type, public_status = http_json(PUBLIC_BASE + '/status')
        vendors_code, vendors_type, public_vendors = http_json(PUBLIC_BASE + '/vendors?limit=1')
        search_code, _, _ = http_json(PUBLIC_BASE + '/search?q=test')

        # This path is intentionally not proxied. Any non-2xx/3xx is acceptable,
        # but evidence count must remain unchanged to prove no backend write occurred.
        post_code, _, _ = http_json(PUBLIC_BASE + '/evidence', method='POST', data={
            'source_type': 'boundary_test',
            'source_url': 'https://example.invalid/vendor-boundary-test'
        })
        local_code_after, _, local_after = http_json(LOCAL_STATUS)
        evidence_after = int(local_after.get('evidence', -2)) if isinstance(local_after, dict) else -2

        if status_code != 200 or 'json' not in status_type or not isinstance(public_status, dict):
            raise RuntimeError('public status acceptance failed')
        if vendors_code != 200 or 'json' not in vendors_type or not isinstance(public_vendors, dict):
            raise RuntimeError('public vendors acceptance failed')
        if search_code not in (200, 422):
            raise RuntimeError('public search acceptance failed')
        if 200 <= post_code < 400:
            raise RuntimeError('public write route unexpectedly accepted request')
        if local_code_after != 200 or evidence_before != evidence_after:
            raise RuntimeError('evidence count changed during write-boundary test')

        result = {
            'schema': 'milkcat.vendor-read-api-nginx-deploy/v1',
            'changed': changed,
            'nginx_test': 'pass',
            'reloaded': changed,
            'public_status': status_code,
            'public_vendors': vendors_code,
            'public_search': search_code,
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
