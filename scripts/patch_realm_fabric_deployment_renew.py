#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'realm_fabric_deployment_renew_v1'
if marker in text:
    print('realm_fabric_deployment_renew=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _realm_fabric_deployment_status(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('deployment status anchor missing')

func = r'''

# realm_fabric_deployment_renew_v1
def _renew_realm_fabric_deployment(params: dict[str, Any]) -> dict[str, Any]:
    import fcntl as _dr_fcntl
    from datetime import datetime as _dr_datetime, timezone as _dr_timezone, timedelta as _dr_timedelta
    import re as _dr_re

    required = {'desired_core_commit', 'lease_owner', 'deployment_generation'}
    optional = {'lease_seconds'}
    if set(params) - (required | optional) or not required.issubset(params):
        raise ValueError('unexpected parameters')
    desired = str(params['desired_core_commit']).strip().lower()
    owner = str(params['lease_owner']).strip()
    generation = int(params['deployment_generation'])
    lease_seconds = int(params.get('lease_seconds') or 900)
    if not _dr_re.fullmatch(r'[0-9a-f]{40}', desired):
        raise ValueError('desired_core_commit must be a 40-hex git commit')
    if not owner or len(owner) > 200:
        raise ValueError('lease_owner required')
    if lease_seconds < 60 or lease_seconds > 3600:
        raise ValueError('lease_seconds out of range')

    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _DEPLOYMENT_LOCK.open('a+', encoding='utf-8') as lock:
        _dr_fcntl.flock(lock.fileno(), _dr_fcntl.LOCK_EX)
        state = _deployment_state_read()
        current_generation = int(state.get('deployment_generation') or 0)
        if current_generation != generation:
            return {'ok': False, 'deployment_status': 'rejected_generation', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('desired_core_commit') != desired:
            return {'ok': False, 'deployment_status': 'rejected_desired', **state, 'observed_core_commit': _observed_realm_commit()}
        if state.get('lease_owner') != owner:
            return {'ok': False, 'deployment_status': 'rejected_lease_owner', **state, 'observed_core_commit': _observed_realm_commit()}
        now = _dr_datetime.now(_dr_timezone.utc)
        renewed = dict(state)
        renewed['lease_expires_at'] = (now + _dr_timedelta(seconds=lease_seconds)).isoformat()
        renewed['updated_at'] = now.isoformat()
        # Renewal is intentionally incapable of changing desired commit or generation.
        renewed['deployment_generation'] = current_generation
        renewed['desired_core_commit'] = desired
        renewed['lease_owner'] = owner
        renewed['observed_core_commit'] = _observed_realm_commit()
        if renewed.get('observed_core_commit') == desired:
            renewed['deployment_status'] = 'converged'
        else:
            renewed['deployment_status'] = 'desired'
        _deployment_state_write(renewed)
        return {'ok': True, **renewed}
'''
text = text.replace(anchor, func + anchor, 1)

mapping = '    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,\n'
if mapping not in text:
    raise SystemExit('deployment status action mapping missing')
text = text.replace(mapping, mapping + '    "agentos.realm-fabric.renew_deployment": _renew_realm_fabric_deployment,\n', 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('realm_fabric_deployment_renew=PASS')
