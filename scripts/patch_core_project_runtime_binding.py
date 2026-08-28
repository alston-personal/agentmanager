#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
marker = 'core_project_runtime_binding_v1'
if marker in text:
    print('core_project_runtime_binding_patch=ALREADY_PRESENT')
    raise SystemExit(0)

old = """    import sys as _pc_sys\n    source_root = Path('/home/ubuntu/agentmanager')\n    if not (source_root / 'agent_core' / 'project_store.py').is_file():\n        return {'ok': False, 'stage': 'source', 'error': 'canonical Core project store unavailable'}\n    if str(source_root) not in _pc_sys.path:\n        _pc_sys.path.insert(0, str(source_root))\n\n    from agent_core.project_store import (\n"""
new = """    import sys as _pc_sys\n    # core_project_runtime_binding_v1: bind mutation logic to the exact deployed Core\n    # release, never to a mutable source checkout that may be refreshed independently.\n    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')\n    if not unit.is_file():\n        return {'ok': False, 'stage': 'runtime_binding', 'error': 'Realm Fabric unit unavailable'}\n    exec_line = ''\n    for raw in unit.read_text(encoding='utf-8').splitlines():\n        if raw.startswith('ExecStart='):\n            exec_line = raw.split('=', 1)[1].strip()\n            break\n    launcher = Path(exec_line.split()[0]) if exec_line else None\n    release_root = launcher.parent.parent if launcher else None\n    if release_root is None or not (release_root / 'agent_core' / 'project_store.py').is_file():\n        return {'ok': False, 'stage': 'runtime_binding', 'error': 'deployed Core project store unavailable', 'exec_start': exec_line}\n    if str(release_root) not in _pc_sys.path:\n        _pc_sys.path.insert(0, str(release_root))\n\n    from agent_core.project_store import (\n"""
if old not in text:
    raise SystemExit('old Core project source binding not found')
text = text.replace(old, new, 1)
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('core_project_runtime_binding_patch=PASS')
