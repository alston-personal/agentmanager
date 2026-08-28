#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
action = 'agentos.realm-fabric.install_release'
if action in text:
    print('realm_fabric_action_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('function insertion anchor not found')

fn = r'''

def _install_realm_fabric_release(params: dict[str, Any]) -> dict[str, Any]:
    """Install one exact AgentOS Core commit as the ubuntu Realm Fabric service.

    The request supplies only a 40-hex source commit. Repository, release root,
    service name, bind address, port, and canonical data root are fixed here.
    No arbitrary path, command, shell, unit, or endpoint is accepted.
    """
    import re as _rf_re
    import shutil as _rf_shutil
    import tempfile as _rf_tempfile
    import urllib.request as _rf_urllib

    if set(params) != {'source_commit'}:
        raise ValueError('unexpected parameters')
    source_commit = str(params.get('source_commit') or '').strip().lower()
    if not _rf_re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('source_commit must be a 40-hex git commit')

    repo = Path('/home/ubuntu/agentmanager')
    if not (repo / '.git').exists():
        return {'ok': False, 'stage': 'source_repo', 'error': 'canonical Core checkout unavailable'}

    realm_root = Path('/home/ubuntu/.local/share/agentos/realm-fabric')
    release = realm_root / 'releases' / source_commit
    current = realm_root / 'current'
    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')
    data_root = Path('/home/ubuntu/agent-data')
    previous = current.resolve() if current.is_symlink() else None
    steps: list[dict[str, Any]] = []

    fetch = _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'fetch', 'origin', source_commit], cwd=repo, timeout=120)
    steps.append({'step': 'fetch_source_commit', **fetch})
    if fetch['returncode'] != 0:
        return {'ok': False, 'stage': 'fetch_source_commit', 'source_commit': source_commit, 'steps': steps}

    with _rf_tempfile.TemporaryDirectory(prefix='realm-fabric-release-') as td:
        checkout = Path(td) / 'source'
        wt = _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'add', '--detach', str(checkout), source_commit], cwd=repo, timeout=90)
        steps.append({'step': 'materialize_source', **wt})
        if wt['returncode'] != 0:
            return {'ok': False, 'stage': 'materialize_source', 'source_commit': source_commit, 'steps': steps}
        try:
            release.mkdir(parents=True, exist_ok=True)
            for name in ('agent_core', 'agentos_node', 'runtime_core'):
                src = checkout / name
                dst = release / name
                if dst.exists():
                    _rf_shutil.rmtree(dst)
                if src.is_dir():
                    _rf_shutil.copytree(src, dst)
            bindir = release / 'bin'
            bindir.mkdir(parents=True, exist_ok=True)
            launcher = bindir / 'agentos-one'
            launcher.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                f'export PYTHONPATH={release}:"${{PYTHONPATH:-}}"\n'
                'exec /usr/bin/python3 -m agent_core.realm_cli "$@"\n',
                encoding='utf-8',
            )
            launcher.chmod(0o755)

            verify = _run([str(launcher), '--help'], cwd=release, timeout=20)
            steps.append({'step': 'verify_launcher', **verify})
            if verify['returncode'] != 0:
                return {'ok': False, 'stage': 'verify_launcher', 'source_commit': source_commit, 'steps': steps}

            realm_id = 'realm-alston'
            env_file = repo / '.env'
            if env_file.is_file():
                for raw in env_file.read_text(encoding='utf-8').splitlines():
                    if raw.startswith('AGENTOS_REALM_ID=') and raw.split('=', 1)[1].strip():
                        realm_id = raw.split('=', 1)[1].strip()
            init = _run([str(launcher), 'init', '--realm-id', realm_id], cwd=release, timeout=30)
            steps.append({'step': 'init_realm', **init})
            if init['returncode'] != 0:
                return {'ok': False, 'stage': 'init_realm', 'source_commit': source_commit, 'steps': steps}

            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text(
                '[Unit]\nDescription=AgentOS ONE Realm Fabric\nAfter=network.target\n\n'
                '[Service]\nType=simple\n'
                f'Environment=AGENT_DATA_ROOT={data_root}\n'
                f'ExecStart={launcher} serve --host 127.0.0.1 --port 8780\n'
                'Restart=always\nRestartSec=5\n'
                f'StandardOutput=append:{data_root}/logs/realm-fabric.log\n'
                f'StandardError=append:{data_root}/logs/realm-fabric.log\n\n'
                '[Install]\nWantedBy=default.target\n',
                encoding='utf-8',
            )

            reload_step = _run(['systemctl', '--user', 'daemon-reload'], cwd=Path.home(), timeout=15)
            steps.append({'step': 'daemon_reload', **reload_step})
            if reload_step['returncode'] != 0:
                return {'ok': False, 'stage': 'daemon_reload', 'source_commit': source_commit, 'steps': steps}
            enable = _run(['systemctl', '--user', 'enable', 'agentos-realm-fabric.service'], cwd=Path.home(), timeout=15)
            steps.append({'step': 'enable_service', **enable})
            if enable['returncode'] != 0:
                return {'ok': False, 'stage': 'enable_service', 'source_commit': source_commit, 'steps': steps}
            restart = _restart_user_service('agentos-realm-fabric.service', timeout=25)
            steps.append({'step': 'restart_service', **restart})
            if not restart.get('ok'):
                if previous and previous.is_dir():
                    current.unlink(missing_ok=True)
                    current.symlink_to(previous)
                return {'ok': False, 'stage': 'restart_service', 'source_commit': source_commit, 'steps': steps}

            health = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    with _rf_urllib.urlopen('http://127.0.0.1:8780/v1/health', timeout=2) as resp:
                        body = resp.read().decode('utf-8', 'replace')
                        health = {'status': resp.status, 'body': body[-4000:]}
                        if resp.status == 200:
                            break
                except Exception as exc:
                    health = {'error': type(exc).__name__ + ': ' + str(exc)}
                time.sleep(0.5)
            if not health or health.get('status') != 200:
                return {'ok': False, 'stage': 'health', 'source_commit': source_commit, 'health': health, 'steps': steps}

            tmp_link = realm_root / f'.current-{source_commit}'
            tmp_link.unlink(missing_ok=True)
            tmp_link.symlink_to(release)
            tmp_link.replace(current)
            return {
                'ok': True,
                'source_commit': source_commit,
                'realm_id': realm_id,
                'release': str(release),
                'current': str(current),
                'service': 'agentos-realm-fabric.service',
                'endpoint': 'http://127.0.0.1:8780',
                'health': health,
                'steps': steps,
            }
        finally:
            _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'remove', '--force', str(checkout)], cwd=repo, timeout=30)
'''
text = text.replace(anchor, fn + anchor, 1)

mapping_anchor = '    "agentos.antigravity.restart": _antigravity_restart,\n'
if mapping_anchor not in text:
    raise SystemExit('ACTIONS insertion anchor not found')
text = text.replace(mapping_anchor, mapping_anchor + '    "agentos.realm-fabric.install_release": _install_realm_fabric_release,\n', 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_action_patch=PASS')
