#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'deployment_rejection_precedence_v1'
if marker in text:
    print('deployment_rejection_precedence=ALREADY_PRESENT')
    raise SystemExit(0)

replacements = {
    "return {'ok': False, 'deployment_status': 'rejected_active_lease', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_active_lease'}",
    "return {'ok': False, 'deployment_status': 'rejected_generation', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_generation'}",
    "return {'ok': False, 'deployment_status': 'rejected_lease_owner', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_lease_owner'}",
    "return {'ok': False, 'deployment_status': 'rejected_current_desired', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_current_desired'}",
    "return {'ok': False, 'deployment_status': 'rejected_not_converged', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_not_converged'}",
    "return {'ok': False, 'deployment_status': 'rejected_desired', **state, 'observed_core_commit': _observed_realm_commit()}":
        "return {**state, 'observed_core_commit': _observed_realm_commit(), 'ok': False, 'deployment_status': 'rejected_desired'}",
}
count = 0
for old, new in replacements.items():
    n = text.count(old)
    if n:
        text = text.replace(old, new)
        count += n
if count == 0:
    raise SystemExit('no deployment rejection merge-order patterns found')
# Marker is deliberately inert and documents governed verdict precedence.
actions_anchor = 'ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {'
if actions_anchor not in text:
    raise SystemExit('ACTIONS mapping anchor not found')
text = text.replace(actions_anchor, '# deployment_rejection_precedence_v1\n' + actions_anchor, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print(f'deployment_rejection_precedence=PASS replacements={count}')
