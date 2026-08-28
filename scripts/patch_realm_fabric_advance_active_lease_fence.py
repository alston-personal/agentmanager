#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_advance_active_lease_fence_v1'
if marker in text:
    print('realm_fabric_advance_active_lease_fence=ALREADY_PRESENT')
    raise SystemExit(0)

advance_anchor = """        state = _deployment_state_read()
        generation = int(state.get('deployment_generation') or 0)
        if generation != expected:
"""
advance_insert = """        state = _deployment_state_read()
        generation = int(state.get('deployment_generation') or 0)
        # realm_fabric_advance_active_lease_fence_v1
        # Generation changes require an explicit release (or natural expiry).
        # The same textual lease_owner is not sufficient authority to replace
        # an actively leased desired generation.
        _lease_status = str(state.get('lease_status') or 'active')
        _lease_expiry = str(state.get('lease_expires_at') or '')
        _lease_active = False
        if _lease_status != 'released' and _lease_expiry:
            try:
                _lease_active = _da_datetime.fromisoformat(_lease_expiry.replace('Z', '+00:00')).astimezone(_da_timezone.utc) > _da_datetime.now(_da_timezone.utc)
            except ValueError:
                _lease_active = True
        if _lease_active:
            return {'ok': False, 'deployment_status': 'rejected_active_lease', **state, 'observed_core_commit': _observed_realm_commit()}
        if generation != expected:
"""
if advance_anchor not in text:
    raise SystemExit('advance state anchor missing')
text = text.replace(advance_anchor, advance_insert, 1)

advanced_anchor = """            'lease_owner': owner,
            'lease_expires_at': (now + _da_timedelta(seconds=lease_seconds)).isoformat(),
            'deployment_status': 'desired',
"""
advanced_insert = """            'lease_owner': owner,
            'lease_expires_at': (now + _da_timedelta(seconds=lease_seconds)).isoformat(),
            'lease_status': 'active',
            'deployment_status': 'desired',
"""
if advanced_anchor not in text:
    raise SystemExit('advanced state anchor missing')
text = text.replace(advanced_anchor, advanced_insert, 1)

status_anchor = '\ndef _realm_fabric_deployment_status(params: dict[str, Any]) -> dict[str, Any]:\n'
if status_anchor not in text:
    raise SystemExit('deployment status anchor missing')
release_func = r'''

# realm_fabric_deployment_release_v1
def _release_realm_fabric_deployment(params: dict[str, Any]) -> dict[str, Any]:
    import fcntl as _rl_fcntl
    from datetime import datetime as _rl_datetime, timezone as _rl_timezone
    import re as _rl_re

    required = {'desired_core_commit', 'lease_owner', 'deployment_generation'}
    if set(params) != required:
        raise ValueError('unexpected parameters')
    desired = str(params['desired_core_commit']).strip().lower()
    owner = str(params['lease_owner']).strip()
    generation = int(params['deployment_generation'])
    if not _rl_re.fullmatch(r'[0-9a-f]{40}', desired):
        raise ValueError('desired_core_commit must be a 40-hex git commit')
    if not owner or len(owner) > 200:
        raise ValueError('lease_owner required')

    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _DEPLOYMENT_LOCK.open('a+', encoding='utf-8') as lock:
        _rl_fcntl.flock(lock.fileno(), _rl_fcntl.LOCK_EX)
        state = _deployment_state_read()
        if int(state.get('deployment_generation') or 0) != generation:
            return {'ok': False, 'deployment_status': 'rejected_generation', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('desired_core_commit') != desired:
            return {'ok': False, 'deployment_status': 'rejected_desired', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('lease_owner') != owner:
            return {'ok': False, 'deployment_status': 'rejected_lease_owner', **state, 'observed_core_commit': _observed_realm_commit()}
        observed = _observed_realm_commit()
        if observed != desired:
            return {'ok': False, 'deployment_status': 'rejected_not_converged', **state, 'observed_core_commit': observed}
        now = _rl_datetime.now(_rl_timezone.utc)
        released = dict(state)
        released.update({
            'observed_core_commit': observed,
            'lease_status': 'released',
            'lease_expires_at': now.isoformat(),
            'released_by': owner,
            'released_at': now.isoformat(),
            'deployment_status': 'converged',
            'updated_at': now.isoformat(),
        })
        _deployment_state_write(released)
        return {'ok': True, **released}
'''
text = text.replace(status_anchor, release_func + status_anchor, 1)

mapping = '    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,\n'
if mapping not in text:
    raise SystemExit('deployment status mapping missing')
text = text.replace(mapping, mapping + '    "agentos.realm-fabric.release_deployment": _release_realm_fabric_deployment,\n', 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_advance_active_lease_fence=PASS')
