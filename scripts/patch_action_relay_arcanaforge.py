#!/usr/bin/env python3
from pathlib import Path

path = Path('agentos_node/action_relay.py')
text = path.read_text(encoding='utf-8')
action = 'github.repo.ensure_arcanaforge'
if action in text:
    print('arcanaforge_action_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = '\ndef _seed_verify_studio_web_remote(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('function insertion anchor not found')

fn = '''\n\ndef _ensure_arcanaforge_remote(params: dict[str, Any]) -> dict[str, Any]:\n    \"\"\"Ensure the one allowlisted ArcanaForge repository exists as private.\n\n    This capability is intentionally narrow: no arbitrary repository name,\n    visibility, description, command, or shell text is accepted. Execution is\n    performed only by the ubuntu Action Relay GitHub identity.\n    \"\"\"\n    if params not in ({}, {\"repository\": \"alston-personal/arcanaforge\"}):\n        raise ValueError(\"unexpected parameters\")\n    repo = \"alston-personal/arcanaforge\"\n    description = \"Symbolic collection generator: SymbolicSystem × Subject × Style, initially Tarot + I Ching, packaging outputs for Divination OS\"\n    auth = _run([\"/usr/bin/gh\", \"auth\", \"status\"], cwd=Path.home(), timeout=20)\n    if auth[\"returncode\"] != 0:\n        return {\"ok\": False, \"repository\": repo, \"auth\": auth, \"created\": False, \"error\": \"ubuntu GitHub identity is not authenticated\"}\n\n    view = _run([\"/usr/bin/gh\", \"repo\", \"view\", repo, \"--json\", \"nameWithOwner,isPrivate,description\"], cwd=Path.home(), timeout=20)\n    created = False\n    create = None\n    if view[\"returncode\"] != 0:\n        create = _run([\n            \"/usr/bin/gh\", \"repo\", \"create\", repo,\n            \"--private\",\n            \"--description\", description,\n        ], cwd=Path.home(), timeout=30)\n        if create[\"returncode\"] != 0:\n            return {\"ok\": False, \"repository\": repo, \"auth\": auth, \"view_before\": view, \"create\": create, \"created\": False}\n        created = True\n        view = _run([\"/usr/bin/gh\", \"repo\", \"view\", repo, \"--json\", \"nameWithOwner,isPrivate,description\"], cwd=Path.home(), timeout=20)\n\n    try:\n        meta = json.loads(view.get(\"stdout\") or \"{}\")\n    except json.JSONDecodeError:\n        meta = {}\n    ok = (\n        view[\"returncode\"] == 0\n        and meta.get(\"nameWithOwner\") == repo\n        and meta.get(\"isPrivate\") is True\n    )\n    return {\"ok\": ok, \"repository\": repo, \"created\": created, \"auth\": auth, \"view\": view, \"create\": create}\n'''
text = text.replace(anchor, fn + anchor, 1)

mapping_anchor = '    "github.repo.ensure_studio_web": _ensure_studio_web_remote,\n'
if mapping_anchor not in text:
    raise SystemExit('ACTIONS insertion anchor not found')
text = text.replace(mapping_anchor, mapping_anchor + '    "github.repo.ensure_arcanaforge": _ensure_arcanaforge_remote,\n', 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('arcanaforge_action_patch=PASS')
