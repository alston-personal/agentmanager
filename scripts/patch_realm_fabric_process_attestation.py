#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_process_attestation_v1'
if marker in text:
    print('realm_fabric_process_attestation=ALREADY_PRESENT')
    raise SystemExit(0)

old_restart = """            restart = _restart_user_service('agentos-realm-fabric.service', timeout=25)
            steps.append({'step': 'restart_service', **restart})
            if not restart.get('ok'):
                if previous and previous.is_dir():
                    current.unlink(missing_ok=True)
                    current.symlink_to(previous)
                return {'ok': False, 'stage': 'restart_service', 'source_commit': source_commit, 'steps': steps}

            health = None
"""
new_restart = """            # realm_fabric_process_attestation_v1
            before_pid_result = _run(['systemctl', '--user', 'show', 'agentos-realm-fabric.service', '--property=MainPID', '--value'], cwd=Path.home(), timeout=10)
            try:
                main_pid_before = int((before_pid_result.get('stdout') or '0').strip() or '0')
            except ValueError:
                main_pid_before = 0
            restart = _restart_user_service('agentos-realm-fabric.service', timeout=25)
            steps.append({'step': 'restart_service', 'main_pid_before': main_pid_before, **restart})
            if not restart.get('ok'):
                if previous and previous.is_dir():
                    current.unlink(missing_ok=True)
                    current.symlink_to(previous)
                return {'ok': False, 'stage': 'restart_service', 'source_commit': source_commit, 'steps': steps}

            main_pid_after = 0
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                pid_result = _run(['systemctl', '--user', 'show', 'agentos-realm-fabric.service', '--property=MainPID', '--value'], cwd=Path.home(), timeout=10)
                try:
                    candidate = int((pid_result.get('stdout') or '0').strip() or '0')
                except ValueError:
                    candidate = 0
                if candidate > 0 and (main_pid_before <= 0 or candidate != main_pid_before):
                    main_pid_after = candidate
                    break
                time.sleep(0.25)
            if main_pid_after <= 0:
                return {'ok': False, 'stage': 'process_identity', 'source_commit': source_commit, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            health = None
"""
if old_restart not in text:
    raise SystemExit('restart block not found')
text = text.replace(old_restart, new_restart, 1)

old_health_return = """            if not health or health.get('status') != 200:
                return {'ok': False, 'stage': 'health', 'source_commit': source_commit, 'health': health, 'steps': steps}

            current_pointer_mode = 'symlink'
"""
new_health_return = """            if not health or health.get('status') != 200:
                return {'ok': False, 'stage': 'health', 'source_commit': source_commit, 'health': health, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            resolve_auth_probe = None
            try:
                req = _rf_urllib.Request(
                    'http://127.0.0.1:8780/v1/resolve',
                    data=json.dumps({'schema':'agentos.resolve-request/v1','node_id':'realm-fabric-deploy-attestation','intent':'continue','project':'agentos-core'}).encode('utf-8'),
                    headers={'Content-Type':'application/json'},
                    method='POST',
                )
                try:
                    with _rf_urllib.urlopen(req, timeout=3) as resp:
                        resolve_auth_probe = {'status': resp.status, 'body': resp.read().decode('utf-8','replace')[-4000:]}
                except _rf_urllib.HTTPError as exc:
                    resolve_auth_probe = {'status': exc.code, 'body': exc.read().decode('utf-8','replace')[-4000:]}
            except Exception as exc:
                resolve_auth_probe = {'error': type(exc).__name__ + ': ' + str(exc)}
            if not resolve_auth_probe or resolve_auth_probe.get('status') != 401:
                return {'ok': False, 'stage': 'resolve_auth_probe', 'source_commit': source_commit, 'health': health, 'resolve_auth_probe': resolve_auth_probe, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            current_pointer_mode = 'symlink'
"""
if old_health_return not in text:
    raise SystemExit('health block not found')
text = text.replace(old_health_return, new_health_return, 1)

old_success = """                'health': health,
                'steps': steps,
            }
"""
new_success = """                'health': health,
                'resolve_auth_probe': resolve_auth_probe,
                'main_pid_before': main_pid_before,
                'main_pid_after': main_pid_after,
                'process_identity_attested': True,
                'steps': steps,
            }
"""
if old_success not in text:
    raise SystemExit('success return block not found')
text = text.replace(old_success, new_success, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_process_attestation=PASS')
