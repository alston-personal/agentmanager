#!/usr/bin/env python3
from pathlib import Path

p = Path('agentos_node/action_relay.py')
s = p.read_text(encoding='utf-8')
if 'github.repo.ensure_studio_web' in s:
    print('already_patched=YES')
    raise SystemExit(0)
needle = "\ndef _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:\n"
fn = r'''

def _ensure_studio_web_remote(params: dict[str, Any]) -> dict[str, Any]:
    """Ensure the one allowlisted Studio Web repository exists as private.

    This action deliberately accepts no arbitrary repo name, visibility, command,
    or shell text. It runs only under the ubuntu Action Relay identity.
    """
    if params not in ({}, {"repository": "alston-personal/studio-web"}):
        raise ValueError("unexpected parameters")
    repo = "alston-personal/studio-web"
    auth = _run(["/usr/bin/gh", "auth", "status"], cwd=Path.home(), timeout=20)
    if auth["returncode"] != 0:
        return {"ok": False, "repository": repo, "auth": auth, "created": False, "error": "ubuntu GitHub identity is not authenticated"}

    view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,visibility"], cwd=Path.home(), timeout=20)
    created = False
    create = None
    if view["returncode"] != 0:
        create = _run([
            "/usr/bin/gh", "repo", "create", repo,
            "--private",
            "--description", "Platform web shell and website-owned integrations for studio.milkcat.org",
        ], cwd=Path.home(), timeout=30)
        if create["returncode"] != 0:
            return {"ok": False, "repository": repo, "auth": auth, "view_before": view, "create": create, "created": False}
        created = True
        view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,visibility"], cwd=Path.home(), timeout=20)

    ok = view["returncode"] == 0 and 'alston-personal/studio-web' in (view.get("stdout") or "") and 'PRIVATE' in (view.get("stdout") or "").upper()
    return {"ok": ok, "repository": repo, "created": created, "auth": auth, "view": view, "create": create}
'''
if needle not in s:
    raise SystemExit('function insertion point missing')
s = s.replace(needle, fn + needle, 1)
map_needle = '    "layoutlab.api.restart": _layoutlab_api_restart,\n'
if map_needle not in s:
    raise SystemExit('action mapping insertion point missing')
s = s.replace(map_needle, '    "github.repo.ensure_studio_web": _ensure_studio_web_remote,\n' + map_needle, 1)
p.write_text(s, encoding='utf-8')
print('action_relay_patch=PASS')
