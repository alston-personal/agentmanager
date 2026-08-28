#!/usr/bin/env python3
from pathlib import Path

path=Path('agentos_node/action_relay.py')
text=path.read_text(encoding='utf-8')
marker='realm_fabric_lease_immutability_v1'
if marker in text:
    print('lease_immutability_patch=ALREADY_PRESENT')
    raise SystemExit(0)
old="""        if active and lease_owner != owner:\n            return {\n                'ok': False,\n                'deployment_status': 'rejected_lease',\n                'desired_core_commit': state.get('desired_core_commit'),\n                'observed_core_commit': _observed_realm_commit(),\n                'deployment_generation': generation,\n                'lease_owner': lease_owner,\n                'lease_expires_at': expires_raw,\n            }\n        if expected != generation:\n"""
new="""        # realm_fabric_lease_immutability_v1: an active lease freezes the desired\n        # generation. Sharing the same owner label must not allow a second workflow\n        # to replace the desired commit. Identical claims are idempotent.\n        if active:\n            if lease_owner == owner and state.get('desired_core_commit') == desired:\n                return {'ok': True, **state, 'claim_status': 'idempotent'}\n            return {\n                'ok': False,\n                'deployment_status': 'rejected_lease',\n                'desired_core_commit': state.get('desired_core_commit'),\n                'observed_core_commit': _observed_realm_commit(),\n                'deployment_generation': generation,\n                'lease_owner': lease_owner,\n                'lease_expires_at': expires_raw,\n            }\n        if expected != generation:\n"""
if old not in text:
    raise SystemExit('lease anchor not found')
text=text.replace(old,new,1)
compile(text,str(path),'exec')
path.write_text(text,encoding='utf-8')
print('lease_immutability_patch=PASS')
