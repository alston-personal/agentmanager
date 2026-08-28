#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/bootstrap_control.py')
text = path.read_text(encoding='utf-8')
marker = 'ACTION_CONTROLLER_SURFACE_INSPECT_VOPC5750'
if marker in text:
    print('bootstrap_controller_probe_patch=ALREADY_PRESENT')
    raise SystemExit(0)

const_anchor = 'ACTION_DEPLOY_REALM_GATEWAY = "agentos.realm_gateway.deploy"\n'
if const_anchor not in text:
    raise SystemExit('bootstrap action constant anchor missing')
text = text.replace(
    const_anchor,
    const_anchor + 'ACTION_CONTROLLER_SURFACE_INSPECT_VOPC5750 = "agentos.controller.surface-inspect-vopc5750"\n',
    1,
)
old_allowed = 'ALLOWED_ACTIONS = {ACTION_REPAIR_TRANSPORT, ACTION_DEPLOY_REALM_GATEWAY}\n'
new_allowed = 'ALLOWED_ACTIONS = {ACTION_REPAIR_TRANSPORT, ACTION_DEPLOY_REALM_GATEWAY, ACTION_CONTROLLER_SURFACE_INSPECT_VOPC5750}\n'
if old_allowed not in text:
    raise SystemExit('bootstrap allowlist anchor missing')
text = text.replace(old_allowed, new_allowed, 1)

exec_anchor = '    if action == ACTION_DEPLOY_REALM_GATEWAY:\n        return _run_canonical_script("scripts/deploy_realm_gateway_user.sh", timeout=300)\n'
if exec_anchor not in text:
    raise SystemExit('bootstrap execute anchor missing')
text = text.replace(
    exec_anchor,
    exec_anchor + '    if action == ACTION_CONTROLLER_SURFACE_INSPECT_VOPC5750:\n        return _run_canonical_script("scripts/controller_surface_inspect_vopc5750.sh", timeout=60)\n',
    1,
)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('bootstrap_controller_probe_patch=PASS')
