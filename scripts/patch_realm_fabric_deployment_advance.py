#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_generation_advance_v1'
if marker in text:
    print('realm_fabric_generation_advance_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _realm_fabric_deployment_status(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('deployment status anchor missing')

func = r'''

# realm_fabric_generation_advance_v1
def _advance_realm_fabric_deployment(params: dict[str, Any]) -> dict[str, Any]:
    import fcntl as _da_fcntl
    from datetime import datetime as _da_datetime, timezone as _da_timezone, timedelta as _da_timedelta
    import re as _da_re

    required = {'current_desired_core_commit', 'next_desired_core_commit', 'lease_owner', 'expected_generation'}
    optional = {'lease_seconds'}
    if set(params) - (required | optional) or not required.issubset(params):
        raise ValueError('unexpected parameters')
    current_desired = str(params['current_desired_core_commit']).strip().lower()
    next_desired = str(params['next_desired_core_commit']).strip().lower()
    owner = str(params['lease_owner']).strip()
    expected = int(params['expected_generation'])
    lease_seconds = int(params.get('lease_seconds') or 900)
    for value in (current_desired, next_desired):
        if not _da_re.fullmatch(r'[0-9a-f]{40}', value):
            raise ValueError('Core commit must be a 40-hex git commit')
    if not owner or len(owner) > 200:
        raise ValueError('lease_owner required')
    if lease_seconds < 60 or lease_seconds > 3600:
        raise ValueError('lease_seconds out of range')

    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _DEPLOYMENT_LOCK.open('a+', encoding='utf-8') as lock:
        _da_fcntl.flock(lock.fileno(), _da_fcntl.LOCK_EX)
        state = _deployment_state_read()
        generation = int(state.get('deployment_generation') or 0)
        if generation != expected:
            return {'ok': False, 'deployment_status': 'rejected_generation', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('lease_owner') != owner:
            return {'ok': False, 'deployment_status': 'rejected_lease_owner', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('desired_core_commit') != current_desired:
            return {'ok': False, 'deployment_status': 'rejected_current_desired', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('observed_core_commit') not in (None, current_desired) and _observed_realm_commit() != current_desired:
            return {'ok': False, 'deployment_status': 'rejected_not_converged', **state, 'observed_core_commit': _observed_realm_commit()}
        now = _da_datetime.now(_da_timezone.utc)
        advanced = {
            'schema': 'agentos.core-deployment/v1',
            'desired_core_commit': next_desired,
            'observed_core_commit': _observed_realm_commit(),
            'deployment_generation': generation + 1,
            'lease_owner': owner,
            'lease_expires_at': (now + _da_timedelta(seconds=lease_seconds)).isoformat(),
            'deployment_status': 'desired',
            'advanced_from_commit': current_desired,
            'advanced_from_generation': generation,
            'updated_at': now.isoformat(),
        }
        _deployment_state_write(advanced)
        return {'ok': True, **advanced}
'''
text = text.replace(anchor, func + anchor, 1)

mapping = '    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,\n'
if mapping not in text:
    raise SystemExit('deployment status action mapping missing')
text = text.replace(mapping, mapping + '    "agentos.realm-fabric.advance_deployment": _advance_realm_fabric_deployment,\n', 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_generation_advance_patch=PASS')
