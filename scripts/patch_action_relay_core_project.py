#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
action = 'agentos.project.register_core'
if action in text:
    print('core_project_action_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _layoutlab_static_deploy(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('function insertion anchor not found')

fn = r'''

def _register_agentos_core_project(params: dict[str, Any]) -> dict[str, Any]:
    """Register the canonical AgentOS Core project through the ubuntu authority boundary.

    This bootstrap action is deliberately fixed: no arbitrary project id, repository,
    checkout path, node id, command, or state path is accepted from the producer.
    """
    if params not in ({}, {'replace': True}):
        raise ValueError('unexpected parameters')

    import sys as _pc_sys
    source_root = Path('/home/ubuntu/agentmanager')
    if not (source_root / 'agent_core' / 'project_store.py').is_file():
        return {'ok': False, 'stage': 'source', 'error': 'canonical Core project store unavailable'}
    if str(source_root) not in _pc_sys.path:
        _pc_sys.path.insert(0, str(source_root))

    from agent_core.project_store import (
        CanonicalProjectRegistration,
        ProjectSourceAuthority,
        project_dir,
        register_canonical_project,
    )

    project_id = 'agentos-core'
    state_dir = project_dir(project_id)
    state_dir.mkdir(parents=True, exist_ok=True)
    status = state_dir / 'STATUS.md'
    if not status.exists():
        status.write_text(
            '# Project Status: agentos-core\n\n'
            '## Current Focus\n'
            'Make ONE the canonical continuation path across nodes, executors, and sessions.\n\n'
            '## Current Acceptance Gate\n'
            'Authenticated live /v1/resolve must return canonical project/source/state authority.\n\n'
            '## Next Action\n'
            'Complete authenticated live resolve acceptance, then connect ChatGPT Web logical node to ONE.\n',
            encoding='utf-8',
        )

    result = register_canonical_project(
        CanonicalProjectRegistration(
            project_id=project_id,
            display_name='AgentOS Core',
            aliases=('AgentOS', 'AgentOS Core'),
            source=ProjectSourceAuthority(
                repo='alston-personal/agentmanager',
                branch='main',
                canonical_path='/home/ubuntu/agentmanager',
                node='oracle-core-node',
            ),
            state_document='STATUS.md',
            phase='active',
            summary='Canonical AgentOS Core development mainline.',
            current_focus='ONE canonical continuation and project authority.',
            next_action='Run authenticated live /v1/resolve acceptance.',
        ),
        replace=bool(params.get('replace')),
    )
    return {'ok': True, **result}
'''
text = text.replace(anchor, fn + anchor, 1)

mapping_anchor = '    "agentos.realm-fabric.install_release": _install_realm_fabric_release,\n'
if mapping_anchor not in text:
    raise SystemExit('ACTIONS insertion anchor not found')
text = text.replace(mapping_anchor, mapping_anchor + '    "agentos.project.register_core": _register_agentos_core_project,\n', 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('core_project_action_patch=PASS')
