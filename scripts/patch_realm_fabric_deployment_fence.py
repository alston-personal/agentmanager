#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_deployment_fence_v1'
if marker in text:
    print('realm_fabric_deployment_fence_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _install_realm_fabric_release(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('install anchor not found')

helpers = r'''

# realm_fabric_deployment_fence_v1
_DEPLOYMENT_STATE = Path('/home/ubuntu/agent-data/governance/core-deployment.json')
_DEPLOYMENT_LOCK = Path('/home/ubuntu/agent-data/governance/core-deployment.lock')


def _deployment_state_read() -> dict[str, Any]:
    if not _DEPLOYMENT_STATE.exists():
        return {
            'schema': 'agentos.core-deployment/v1',
            'deployment_generation': 0,
            'desired_core_commit': None,
            'observed_core_commit': None,
            'lease_owner': None,
            'lease_expires_at': None,
            'deployment_status': 'uninitialized',
        }
    data = json.loads(_DEPLOYMENT_STATE.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('invalid Core deployment state')
    return data


def _deployment_state_write(state: dict[str, Any]) -> None:
    _DEPLOYMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DEPLOYMENT_STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    _share(tmp)
    tmp.replace(_DEPLOYMENT_STATE)
    _share(_DEPLOYMENT_STATE)


def _observed_realm_commit() -> str | None:
    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')
    if not unit.is_file():
        return None
    for raw in unit.read_text(encoding='utf-8').splitlines():
        if not raw.startswith('ExecStart='):
            continue
        value = raw.split('=', 1)[1]
        parts = value.split('/realm-fabric/releases/', 1)
        if len(parts) != 2:
            return None
        commit = parts[1].split('/', 1)[0].strip().lower()
        if len(commit) == 40 and all(c in '0123456789abcdef' for c in commit):
            return commit
    return None


def _claim_realm_fabric_deployment(params: dict[str, Any]) -> dict[str, Any]:
    import fcntl as _df_fcntl
    from datetime import datetime as _df_datetime, timezone as _df_timezone, timedelta as _df_timedelta
    import re as _df_re

    required = {'desired_core_commit', 'lease_owner', 'expected_generation'}
    optional = {'lease_seconds'}
    if set(params) - (required | optional) or not required.issubset(params):
        raise ValueError('unexpected parameters')
    desired = str(params['desired_core_commit']).strip().lower()
    owner = str(params['lease_owner']).strip()
    expected = int(params['expected_generation'])
    lease_seconds = int(params.get('lease_seconds') or 900)
    if not _df_re.fullmatch(r'[0-9a-f]{40}', desired):
        raise ValueError('desired_core_commit must be a 40-hex git commit')
    if not owner or len(owner) > 200:
        raise ValueError('lease_owner required')
    if lease_seconds < 60 or lease_seconds > 3600:
        raise ValueError('lease_seconds out of range')

    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _DEPLOYMENT_LOCK.open('a+', encoding='utf-8') as lock:
        _df_fcntl.flock(lock.fileno(), _df_fcntl.LOCK_EX)
        state = _deployment_state_read()
        generation = int(state.get('deployment_generation') or 0)
        now = _df_datetime.now(_df_timezone.utc)
        lease_owner = state.get('lease_owner')
        expires_raw = state.get('lease_expires_at')
        active = False
        if lease_owner and expires_raw:
            try:
                active = _df_datetime.fromisoformat(str(expires_raw)) > now
            except ValueError:
                active = False
        if active and lease_owner != owner:
            return {
                'ok': False,
                'deployment_status': 'rejected_lease',
                'desired_core_commit': state.get('desired_core_commit'),
                'observed_core_commit': _observed_realm_commit(),
                'deployment_generation': generation,
                'lease_owner': lease_owner,
                'lease_expires_at': expires_raw,
            }
        if expected != generation:
            return {
                'ok': False,
                'deployment_status': 'rejected_generation',
                'desired_core_commit': state.get('desired_core_commit'),
                'observed_core_commit': _observed_realm_commit(),
                'deployment_generation': generation,
                'lease_owner': lease_owner,
                'lease_expires_at': expires_raw,
            }
        new_generation = generation + 1
        state = {
            'schema': 'agentos.core-deployment/v1',
            'desired_core_commit': desired,
            'observed_core_commit': _observed_realm_commit(),
            'deployment_generation': new_generation,
            'lease_owner': owner,
            'lease_expires_at': (now + _df_timedelta(seconds=lease_seconds)).isoformat(),
            'deployment_status': 'desired',
            'updated_at': now.isoformat(),
        }
        _deployment_state_write(state)
        return {'ok': True, **state}


def _realm_fabric_deployment_status(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({},):
        raise ValueError('unexpected parameters')
    state = _deployment_state_read()
    state['observed_core_commit'] = _observed_realm_commit()
    if state.get('desired_core_commit') and state.get('desired_core_commit') == state.get('observed_core_commit'):
        state['deployment_status'] = 'converged'
    return {'ok': True, **state}
'''
text = text.replace(anchor, helpers + anchor, 1)

old_validate = """    if set(params) != {'source_commit'}:\n        raise ValueError('unexpected parameters')\n    source_commit = str(params.get('source_commit') or '').strip().lower()\n"""
new_validate = """    required = {'source_commit', 'desired_core_commit', 'lease_owner', 'deployment_generation'}\n    if set(params) != required:\n        raise ValueError('unexpected parameters')\n    source_commit = str(params.get('source_commit') or '').strip().lower()\n    desired_core_commit = str(params.get('desired_core_commit') or '').strip().lower()\n    lease_owner = str(params.get('lease_owner') or '').strip()\n    deployment_generation = int(params.get('deployment_generation'))\n"""
if old_validate not in text:
    raise SystemExit('install validation anchor not found')
text = text.replace(old_validate, new_validate, 1)

old_after_hex = """    if not _rf_re.fullmatch(r'[0-9a-f]{40}', source_commit):\n        raise ValueError('source_commit must be a 40-hex git commit')\n\n    repo = Path('/home/ubuntu/agentmanager')\n"""
new_after_hex = """    if not _rf_re.fullmatch(r'[0-9a-f]{40}', source_commit):\n        raise ValueError('source_commit must be a 40-hex git commit')\n    if desired_core_commit != source_commit:\n        return {'ok': False, 'deployment_status': 'rejected_desired_mismatch', 'source_commit': source_commit, 'desired_core_commit': desired_core_commit}\n\n    import fcntl as _rf_fcntl\n    from datetime import datetime as _rf_datetime, timezone as _rf_timezone\n    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)\n    _deployment_guard = _DEPLOYMENT_LOCK.open('a+', encoding='utf-8')\n    _rf_fcntl.flock(_deployment_guard.fileno(), _rf_fcntl.LOCK_EX)\n    _deployment_state = _deployment_state_read()\n    _current_generation = int(_deployment_state.get('deployment_generation') or 0)\n    _lease_expires = _deployment_state.get('lease_expires_at')\n    try:\n        _lease_active = bool(_lease_expires) and _rf_datetime.fromisoformat(str(_lease_expires)) > _rf_datetime.now(_rf_timezone.utc)\n    except ValueError:\n        _lease_active = False\n    if (\n        _current_generation != deployment_generation\n        or _deployment_state.get('desired_core_commit') != source_commit\n        or _deployment_state.get('lease_owner') != lease_owner\n        or not _lease_active\n    ):\n        _deployment_guard.close()\n        return {\n            'ok': False,\n            'deployment_status': 'rejected_fence',\n            'source_commit': source_commit,\n            'desired_core_commit': _deployment_state.get('desired_core_commit'),\n            'observed_core_commit': _observed_realm_commit(),\n            'deployment_generation': _current_generation,\n            'lease_owner': _deployment_state.get('lease_owner'),\n            'lease_expires_at': _deployment_state.get('lease_expires_at'),\n        }\n\n    repo = Path('/home/ubuntu/agentmanager')\n"""
if old_after_hex not in text:
    raise SystemExit('install preflight anchor not found')
text = text.replace(old_after_hex, new_after_hex, 1)

old_return = """            return {\n                'ok': True,\n                'source_commit': source_commit,\n"""
new_return = """            _deployment_state['observed_core_commit'] = source_commit\n            _deployment_state['deployment_status'] = 'converged'\n            _deployment_state['updated_at'] = _rf_datetime.now(_rf_timezone.utc).isoformat()\n            _deployment_state_write(_deployment_state)\n            return {\n                'ok': True,\n                'deployment_status': 'converged',\n                'desired_core_commit': source_commit,\n                'observed_core_commit': source_commit,\n                'deployment_generation': deployment_generation,\n                'lease_owner': lease_owner,\n                'lease_expires_at': _deployment_state.get('lease_expires_at'),\n                'source_commit': source_commit,\n"""
if old_return not in text:
    raise SystemExit('success return anchor not found')
text = text.replace(old_return, new_return, 1)

finally_anchor = """        finally:\n            _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'remove', '--force', str(checkout)], cwd=repo, timeout=30)\n"""
finally_repl = """        finally:\n            _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'remove', '--force', str(checkout)], cwd=repo, timeout=30)\n            _deployment_guard.close()\n"""
if finally_anchor not in text:
    raise SystemExit('finally anchor not found')
text = text.replace(finally_anchor, finally_repl, 1)

mapping = '    "agentos.realm-fabric.install_release": _install_realm_fabric_release,\n'
if mapping not in text:
    raise SystemExit('action mapping anchor not found')
text = text.replace(mapping, '    "agentos.realm-fabric.claim_deployment": _claim_realm_fabric_deployment,\n    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,\n' + mapping, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_deployment_fence_patch=PASS')
