#!/usr/bin/env python3
from pathlib import Path

p = Path('agentos_node/action_relay.py')
s = p.read_text(encoding='utf-8')
marker = 'agentos.project.publish_continuation'
if marker in s:
    print('already_patched=YES')
    raise SystemExit(0)

needle = '\ndef _antigravity_restart(params: dict[str, Any]) -> dict[str, Any]:\n'
fn = r'''

def _publish_project_continuation(params: dict[str, Any]) -> dict[str, Any]:
    """Publish the canonical AgentOS Core continuation through one narrow action.

    The relay accepts no arbitrary path or shell. Project identity, mutation
    authority, schemas, index generation, and canonical target paths are all
    revalidated by the publisher under the ubuntu execution identity.
    """
    from agent_core.project_continuation_index import publish_project_continuation
    return publish_project_continuation(params)
'''
if needle not in s:
    raise SystemExit('function insertion point missing')
s = s.replace(needle, fn + needle, 1)

map_needle = '    "agentos.antigravity.restart": _antigravity_restart,\n'
if map_needle not in s:
    raise SystemExit('action mapping insertion point missing')
s = s.replace(map_needle, map_needle + '    "agentos.project.publish_continuation": _publish_project_continuation,\n', 1)
p.write_text(s, encoding='utf-8')
print('action_relay_project_continuation_patch=PASS')
