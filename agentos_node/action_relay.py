from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from typing import Any, Callable
import uuid
from datetime import datetime, timezone

ACTION_SCHEMA = "agentos.action-relay/v1"
RECEIPT_SCHEMA = "agentos.action-receipt/v1"
SHARED_GROUP = "agentos"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _share(path: Path, *, directory: bool = False) -> None:
    """Normalize a relay path or accept an already-secure cross-owner handoff.

    Producers and the ubuntu worker share the `agentos` group but intentionally
    keep distinct owners. After a producer-owned capsule is atomically renamed
    into `processing`, ubuntu is allowed to continue if the inherited group and
    mode are already exactly the governed values; group membership alone does
    not grant chmod/chown of another user's file.
    """
    gid = grp.getgrnam(SHARED_GROUP).gr_gid
    desired_mode = 0o2770 if directory else 0o660
    try:
        os.chown(path, -1, gid)
    except PermissionError:
        if path.stat().st_gid != gid:
            raise
    try:
        os.chmod(path, desired_mode)
    except PermissionError:
        current = path.stat()
        if current.st_gid != gid or stat.S_IMODE(current.st_mode) != desired_mode:
            raise


class Paths:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.processing = self.root / "processing"
        self.receipts = self.root / "receipts"
        self.quarantine = self.root / "quarantine"

    def ensure(self) -> None:
        for p in (self.root, self.inbox, self.processing, self.receipts, self.quarantine):
            p.mkdir(parents=True, exist_ok=True)
            _share(p, directory=True)


class ActionRelayClient:
    """Producer API. No command/shell text exists in the capsule contract."""

    def __init__(self, root: str | Path): self.paths = Paths(root)

    def submit(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        action = str(action or "").strip()
        if not action or not isinstance(params or {}, dict): raise ValueError("action and object params are required")
        if action not in ACTIONS: raise ValueError(f"unsupported action: {action}")
        self.paths.ensure(); capsule_id = f"action-{uuid.uuid4().hex}"
        payload: dict[str, Any] = {"schema": ACTION_SCHEMA,"capsule_id": capsule_id,"created_at": _now(),"action": action,"params": params or {},"authority": {"source": "agentos-node", "target_user": "ubuntu", "arbitrary_shell": False}}
        payload["digest"] = "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()
        tmp = self.paths.inbox / f"{capsule_id}.json.tmp"; target = self.paths.inbox / f"{capsule_id}.json"
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _share(tmp); tmp.replace(target); _share(target)
        return payload

    def receipt(self, capsule_id: str) -> dict[str, Any] | None:
        p = self.paths.receipts / f"{capsule_id}.json"
        if not p.exists(): return None
        result = json.loads(p.read_text(encoding="utf-8"))
        if result.get("schema") != RECEIPT_SCHEMA: raise ValueError("invalid receipt")
        return result


def _run(argv: list[str], *, cwd: str | Path, timeout: int = 300) -> dict[str, Any]:
    completed = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
    return {"argv": argv, "returncode": completed.returncode, "stdout": completed.stdout[-30000:], "stderr": completed.stderr[-10000:]}


def _restart_user_service(unit: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Restart a user unit without letting systemctl's job wait pin the relay."""
    cwd = Path.home()
    restart = _run(["systemctl", "--user", "--no-block", "restart", unit], cwd=cwd, timeout=8)
    observations: list[dict[str, Any]] = []
    if restart["returncode"] != 0:
        return {"ok": False, "service": unit, "restart": restart, "observations": observations}

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = _run(["systemctl", "--user", "is-active", unit], cwd=cwd, timeout=5)
        state = (probe.get("stdout") or "").strip()
        observations.append({"returncode": probe["returncode"], "state": state, "stderr": probe.get("stderr", "")[-2000:]})
        if probe["returncode"] == 0 and state == "active":
            return {"ok": True, "service": unit, "restart": restart, "observations": observations}
        time.sleep(0.5)
    return {"ok": False, "service": unit, "restart": restart, "observations": observations, "error": "service did not become active before deadline"}


def _site_sync_build(params: dict[str, Any]) -> dict[str, Any]:
    site = params.get("site")
    if site != "studio.milkcat.org": raise ValueError("site is not allowlisted")
    repo = Path("/home/ubuntu/zeus-writer"); website = repo / "website"
    if not (repo / ".git").exists() or not (website / "package.json").exists(): raise RuntimeError("allowlisted site checkout unavailable")
    git = ["git", "-c", f"safe.directory={repo}", "-C", str(repo)]
    dirty = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
    if dirty: raise RuntimeError("site checkout is dirty; refusing automated sync")
    steps = [_run(git + ["fetch", "origin", "master"], cwd=repo)]
    if steps[-1]["returncode"] != 0: return {"ok": False, "steps": steps}
    steps.append(_run(git + ["merge", "--ff-only", "origin/master"], cwd=repo))
    if steps[-1]["returncode"] != 0: return {"ok": False, "steps": steps}
    steps.append(_run(["npm", "run", "build"], cwd=website, timeout=600))
    ok = steps[-1]["returncode"] == 0 and (website / "dist" / "layout-lab" / "index.html").exists()
    return {"ok": ok, "site": site, "artifact": str(website / "dist" / "layout-lab" / "index.html"), "steps": steps}



def _register_agentos_core_project(params: dict[str, Any]) -> dict[str, Any]:
    """Register the canonical AgentOS Core project through the ubuntu authority boundary.

    This bootstrap action is deliberately fixed: no arbitrary project id, repository,
    checkout path, node id, command, or state path is accepted from the producer.
    """
    if params not in ({}, {'replace': True}):
        raise ValueError('unexpected parameters')

    import sys as _pc_sys
    # core_project_runtime_binding_v1: bind mutation logic to the exact deployed Core
    # release, never to a mutable source checkout that may be refreshed independently.
    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')
    if not unit.is_file():
        return {'ok': False, 'stage': 'runtime_binding', 'error': 'Realm Fabric unit unavailable'}
    exec_line = ''
    for raw in unit.read_text(encoding='utf-8').splitlines():
        if raw.startswith('ExecStart='):
            exec_line = raw.split('=', 1)[1].strip()
            break
    launcher = Path(exec_line.split()[0]) if exec_line else None
    release_root = launcher.parent.parent if launcher else None
    if release_root is None or not (release_root / 'agent_core' / 'project_store.py').is_file():
        return {'ok': False, 'stage': 'runtime_binding', 'error': 'deployed Core project store unavailable', 'exec_start': exec_line}
    if str(release_root) not in _pc_sys.path:
        _pc_sys.path.insert(0, str(release_root))

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

def _layoutlab_static_deploy(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"site": "studio.milkcat.org"}): raise ValueError("unexpected parameters")
    runtime_root = Path(__file__).resolve().parents[1]
    script = runtime_root / "scripts/deploy_layoutlab_static.py"
    if not script.is_file(): raise RuntimeError(f"static deploy script missing: {script}")
    step = _run(["/usr/bin/python3", str(script)], cwd=runtime_root, timeout=30)
    ok = step["returncode"] == 0
    return {
        "ok": ok,
        "site": "studio.milkcat.org",
        "artifact": "/home/ubuntu/zeus-writer/website/dist/layout-lab/index.html",
        "mode": "browser-only-layoutlib-v0.1-compatible",
        "step": step,
    }



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



def _ensure_arcanaforge_remote(params: dict[str, Any]) -> dict[str, Any]:
    """Ensure the one allowlisted ArcanaForge repository exists as private.

    This capability is intentionally narrow: no arbitrary repository name,
    visibility, description, command, or shell text is accepted. Execution is
    performed only by the ubuntu Action Relay GitHub identity.
    """
    if params not in ({}, {"repository": "alston-personal/arcanaforge"}):
        raise ValueError("unexpected parameters")
    repo = "alston-personal/arcanaforge"
    description = "Symbolic collection generator: SymbolicSystem × Subject × Style, initially Tarot + I Ching, packaging outputs for Divination OS"
    auth = _run(["/usr/bin/gh", "auth", "status"], cwd=Path.home(), timeout=20)
    if auth["returncode"] != 0:
        return {"ok": False, "repository": repo, "auth": auth, "created": False, "error": "ubuntu GitHub identity is not authenticated"}

    view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate,description"], cwd=Path.home(), timeout=20)
    created = False
    create = None
    if view["returncode"] != 0:
        create = _run([
            "/usr/bin/gh", "repo", "create", repo,
            "--private",
            "--description", description,
        ], cwd=Path.home(), timeout=30)
        if create["returncode"] != 0:
            return {"ok": False, "repository": repo, "auth": auth, "view_before": view, "create": create, "created": False}
        created = True
        view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate,description"], cwd=Path.home(), timeout=20)

    try:
        meta = json.loads(view.get("stdout") or "{}")
    except json.JSONDecodeError:
        meta = {}
    ok = (
        view["returncode"] == 0
        and meta.get("nameWithOwner") == repo
        and meta.get("isPrivate") is True
    )
    return {"ok": ok, "repository": repo, "created": created, "auth": auth, "view": view, "create": create}


def _ensure_layoutlib_remote(params: dict[str, Any]) -> dict[str, Any]:
    """Ensure the one allowlisted LayoutLib repository exists as private.

    This capability is intentionally narrow: no arbitrary repository name,
    visibility, description, command, or shell text is accepted. Execution is
    performed only by the ubuntu Action Relay GitHub identity.
    """
    if params not in ({}, {"repository": "alston-personal/layoutlib"}):
        raise ValueError("unexpected parameters")
    repo = "alston-personal/layoutlib"
    description = "LayoutLib spatial layout library with the Layout Lab reference demo"
    auth = _run(["/usr/bin/gh", "auth", "status"], cwd=Path.home(), timeout=20)
    if auth["returncode"] != 0:
        return {"ok": False, "repository": repo, "auth": auth, "created": False, "error": "ubuntu GitHub identity is not authenticated"}

    view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate,description"], cwd=Path.home(), timeout=20)
    created = False
    create = None
    if view["returncode"] != 0:
        create = _run([
            "/usr/bin/gh", "repo", "create", repo,
            "--private",
            "--description", description,
        ], cwd=Path.home(), timeout=30)
        if create["returncode"] != 0:
            return {"ok": False, "repository": repo, "auth": auth, "view_before": view, "create": create, "created": False}
        created = True
        view = _run(["/usr/bin/gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate,description"], cwd=Path.home(), timeout=20)

    try:
        meta = json.loads(view.get("stdout") or "{}")
    except json.JSONDecodeError:
        meta = {}
    ok = (
        view["returncode"] == 0
        and meta.get("nameWithOwner") == repo
        and meta.get("isPrivate") is True
    )
    return {"ok": ok, "repository": repo, "created": created, "auth": auth, "view": view, "create": create}


def _import_layoutlib_v079(params: dict[str, Any]) -> dict[str, Any]:
    """Import the fixed LayoutLib v0.7.9 production package into its canonical repo."""
    import hashlib as _ll_hashlib
    import json as _ll_json
    import shutil as _ll_shutil
    import subprocess as _ll_subprocess
    import tempfile as _ll_tempfile
    from pathlib import Path as _LLPath

    source_repo = 'alston-personal/agentmanager'
    source_commit = 'e8efc4ed7cbd41839f960373f79c5fb6a5f82375'
    target_repo = 'alston-personal/layoutlib'
    release = 'v0.7.9'
    files = [
        'web_assets/layoutlab_v0_5.html',
        'web_assets/layoutlib-browser-v0.5.js',
        'web_assets/layoutlib-spatial-semantics-v0.1.js',
        'web_assets/layoutlib-editor-v0.7.js',
        'web_assets/layoutlab-editor-ui-v0.7.js',
        'web_assets/layoutlab-capability-bridge-v0.7.js',
        'web_assets/layoutlab-v0.7-release-fix.js',
    ]
    expected = {'repository': target_repo, 'source_commit': source_commit}
    if params not in ({}, expected):
        raise ValueError('unexpected parameters')

    def run(argv, cwd=None, timeout=90):
        p = _ll_subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
        return {'argv': argv, 'returncode': p.returncode, 'stdout': p.stdout[-4000:], 'stderr': p.stderr[-4000:]}

    auth = run(['/usr/bin/gh', 'auth', 'status'], cwd=str(_LLPath.home()), timeout=20)
    if auth['returncode'] != 0:
        return {'ok': False, 'error': 'ubuntu GitHub identity is not authenticated', 'auth': auth}

    with _ll_tempfile.TemporaryDirectory(prefix='layoutlib-v079-import-') as td:
        root = _LLPath(td)
        src = root / 'source'
        dst = root / 'layoutlib'
        clone_src = run(['/usr/bin/gh', 'repo', 'clone', source_repo, str(src)], timeout=120)
        if clone_src['returncode'] != 0:
            return {'ok': False, 'stage': 'clone_source', 'clone_source': clone_src}
        checkout = run(['/usr/bin/git', '-C', str(src), 'checkout', '--detach', source_commit], timeout=60)
        if checkout['returncode'] != 0:
            return {'ok': False, 'stage': 'checkout_source', 'checkout': checkout}

        source_hashes = {}
        for rel in files:
            p = src / rel
            if not p.is_file():
                return {'ok': False, 'stage': 'source_manifest', 'missing': rel}
            source_hashes[rel] = _ll_hashlib.sha256(p.read_bytes()).hexdigest()

        clone_dst = run(['/usr/bin/gh', 'repo', 'clone', target_repo, str(dst)], timeout=120)
        if clone_dst['returncode'] != 0:
            return {'ok': False, 'stage': 'clone_target', 'clone_target': clone_dst}
        branch = run(['/usr/bin/git', '-C', str(dst), 'checkout', '-B', 'main'], timeout=30)
        if branch['returncode'] != 0:
            return {'ok': False, 'stage': 'checkout_target', 'checkout_target': branch}

        release_dir = dst / 'release' / release
        release_dir.mkdir(parents=True, exist_ok=True)
        for rel in files:
            _ll_shutil.copy2(src / rel, release_dir / _LLPath(rel).name)

        provenance = f"""# LayoutLib {release} production extraction

Canonical source extraction from `{source_repo}` at exact commit `{source_commit}`.

The files in this directory are the seven assets used by the authoritative Oracle `Layout Lab v0.7` production release path. They are preserved flat so historical release identity remains auditable.

## Ownership boundary

- LayoutLib library/parser/editor semantics: `layoutlib-browser-v0.5.js`, `layoutlib-spatial-semantics-v0.1.js`, `layoutlib-editor-v0.7.js`.
- Layout Lab reference/demo surface: `layoutlab_v0_5.html`, `layoutlab-editor-ui-v0.7.js`, `layoutlab-capability-bridge-v0.7.js`, `layoutlab-v0.7-release-fix.js`.
- The historical filename `layoutlib-browser-v0.5.js` identifies itself internally as Browser Adapter v0.6.0; it is intentionally not renamed in this extraction.

This extraction is provenance-preserving. Refactoring/version normalization must be a later, separately reviewed change.
"""
        (release_dir / 'PROVENANCE.md').write_text(provenance, encoding='utf-8')
        manifest = {
            'schema': 'layoutlib.production-extraction/v1',
            'release': release,
            'source_repository': source_repo,
            'source_commit': source_commit,
            'files': [
                {
                    'source': rel,
                    'destination': f'release/{release}/{_LLPath(rel).name}',
                    'sha256': source_hashes[rel],
                }
                for rel in files
            ],
        }
        (release_dir / 'manifest.json').write_text(_ll_json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        readme = f"""# LayoutLib

Canonical repository for the LayoutLib spatial layout library.

The first canonicalized production snapshot is preserved under `release/{release}/`, extracted byte-for-byte from `{source_repo}@{source_commit}`. Layout Lab files in that snapshot are historical reference/demo surface assets, not LayoutLib project identity.
"""
        (dst / 'README.md').write_text(readme, encoding='utf-8')

        for key, value in [('user.name', 'AgentOS Oracle Core'), ('user.email', 'agentos-core@users.noreply.github.com')]:
            cfg = run(['/usr/bin/git', '-C', str(dst), 'config', key, value])
            if cfg['returncode'] != 0:
                return {'ok': False, 'stage': 'git_config', 'git_config': cfg}
        add = run(['/usr/bin/git', '-C', str(dst), 'add', 'README.md', f'release/{release}'])
        if add['returncode'] != 0:
            return {'ok': False, 'stage': 'git_add', 'git_add': add}
        status = run(['/usr/bin/git', '-C', str(dst), 'status', '--porcelain'])
        changed = bool(status['stdout'].strip())
        if changed:
            commit = run(['/usr/bin/git', '-C', str(dst), 'commit', '-m', 'chore: import canonical LayoutLib v0.7.9 production snapshot'], timeout=60)
            if commit['returncode'] != 0:
                return {'ok': False, 'stage': 'git_commit', 'git_commit': commit}
            push = run(['/usr/bin/git', '-C', str(dst), 'push', 'origin', 'HEAD:main'], timeout=120)
            if push['returncode'] != 0:
                return {'ok': False, 'stage': 'git_push', 'git_push': push}
        head = run(['/usr/bin/git', '-C', str(dst), 'rev-parse', 'HEAD'])
        if head['returncode'] != 0:
            return {'ok': False, 'stage': 'head', 'head': head}
        target_commit = head['stdout'].strip()

        destination_hashes = {}
        for rel in files:
            name = _LLPath(rel).name
            p = release_dir / name
            destination_hashes[name] = _ll_hashlib.sha256(p.read_bytes()).hexdigest()
            if destination_hashes[name] != source_hashes[rel]:
                return {'ok': False, 'stage': 'hash_verify', 'file': name}

        return {
            'ok': True,
            'repository': target_repo,
            'release': release,
            'source_repository': source_repo,
            'source_commit': source_commit,
            'target_commit': target_commit,
            'changed': changed,
            'file_count': len(files),
            'source_sha256': source_hashes,
            'destination_sha256': destination_hashes,
        }

def _seed_verify_studio_web_remote(params: dict[str, Any]) -> dict[str, Any]:
    """Push the one governed Studio Web checkout and prove remote rebuildability."""
    if params not in ({}, {"repository": "alston-personal/studio-web"}):
        raise ValueError("unexpected parameters")
    repository = "alston-personal/studio-web"
    source = Path("/home/agentos-node/projects/studio-web")
    if not (source / ".git").exists() or not (source / "package.json").is_file():
        return {"ok": False, "repository": repository, "error": "governed source checkout unavailable"}

    steps: list[dict[str, Any]] = []
    git_prefix = ["git", "-c", f"safe.directory={source}", "-C", str(source)]
    status = _run(git_prefix + ["status", "--porcelain"], cwd=Path.home(), timeout=20)
    steps.append({"step": "source_status", **status})
    if status["returncode"] != 0 or (status.get("stdout") or "").strip():
        return {"ok": False, "repository": repository, "steps": steps, "error": "source checkout is not clean"}

    head = _run(git_prefix + ["rev-parse", "HEAD"], cwd=Path.home(), timeout=20)
    steps.append({"step": "source_head", **head})
    if head["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps}
    source_head = (head.get("stdout") or "").strip()

    auth = _run(["/usr/bin/gh", "auth", "status"], cwd=Path.home(), timeout=20)
    steps.append({"step": "gh_auth", **auth})
    if auth["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps, "error": "ubuntu GitHub identity is not authenticated"}

    view = _run(["/usr/bin/gh", "repo", "view", repository, "--json", "nameWithOwner,isPrivate"], cwd=Path.home(), timeout=20)
    steps.append({"step": "remote_view", **view})
    if view["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps, "error": "remote repository unavailable"}
    try:
        meta = json.loads(view.get("stdout") or "{}")
    except json.JSONDecodeError:
        meta = {}
    if meta.get("nameWithOwner") != repository or meta.get("isPrivate") is not True:
        return {"ok": False, "repository": repository, "steps": steps, "error": "remote identity/visibility mismatch"}

    setup = _run(["/usr/bin/gh", "auth", "setup-git"], cwd=Path.home(), timeout=20)
    steps.append({"step": "gh_auth_setup_git", **setup})
    if setup["returncode"] != 0:
        return {"ok": False, "repository": repository, "steps": steps}

    push = _run(git_prefix + ["push", "https://github.com/alston-personal/studio-web.git", "HEAD:main"], cwd=Path.home(), timeout=120)
    steps.append({"step": "initial_push", **push})
    if push["returncode"] != 0:
        return {"ok": False, "repository": repository, "source_head": source_head, "steps": steps}

    verify_root = Path("/tmp") / f"studio-web-remote-verify-{uuid.uuid4().hex}"
    clone = _run(["/usr/bin/gh", "repo", "clone", repository, str(verify_root)], cwd=Path.home(), timeout=120)
    steps.append({"step": "fresh_clone", **clone})
    if clone["returncode"] != 0:
        return {"ok": False, "repository": repository, "source_head": source_head, "steps": steps}

    try:
        remote_head_step = _run(["git", "-C", str(verify_root), "rev-parse", "HEAD"], cwd=Path.home(), timeout=20)
        steps.append({"step": "remote_head", **remote_head_step})
        remote_head = (remote_head_step.get("stdout") or "").strip()
        if remote_head_step["returncode"] != 0 or remote_head != source_head:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "steps": steps, "error": "remote head mismatch"}

        if (verify_root / "pnpm-lock.yaml").is_file():
            install_argv = ["pnpm", "install", "--frozen-lockfile"]
            build_argv = ["pnpm", "run", "build"]
            package_manager = "pnpm"
        elif (verify_root / "package-lock.json").is_file():
            install_argv = ["npm", "ci"]
            build_argv = ["npm", "run", "build"]
            package_manager = "npm"
        elif (verify_root / "yarn.lock").is_file():
            install_argv = ["yarn", "install", "--frozen-lockfile"]
            build_argv = ["yarn", "run", "build"]
            package_manager = "yarn"
        else:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "steps": steps, "error": "supported lockfile missing"}

        install = _run(install_argv, cwd=verify_root, timeout=600)
        steps.append({"step": "fresh_install", **install})
        if install["returncode"] != 0:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps}

        build = _run(build_argv, cwd=verify_root, timeout=600)
        steps.append({"step": "fresh_build", **build})
        if build["returncode"] != 0:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps}

        home = verify_root / "dist" / "index.html"
        layout_source = verify_root / "public" / "layout-lab" / "index.html"
        layout_dist = verify_root / "dist" / "layout-lab" / "index.html"
        if not home.is_file() or not layout_source.is_file() or not layout_dist.is_file():
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps, "error": "required built artifact missing"}
        layout_bytes = layout_dist.read_bytes()
        if b"Layout Lab | Milkcat Studio" not in layout_bytes or b"Analyze layout" not in layout_bytes:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "steps": steps, "error": "Layout Lab identity marker missing"}
        source_sha = hashlib.sha256(layout_source.read_bytes()).hexdigest()
        dist_sha = hashlib.sha256(layout_bytes).hexdigest()
        home_sha = hashlib.sha256(home.read_bytes()).hexdigest()
        if source_sha != dist_sha:
            return {"ok": False, "repository": repository, "source_head": source_head, "remote_head": remote_head, "package_manager": package_manager, "layout_source_sha256": source_sha, "layout_dist_sha256": dist_sha, "steps": steps, "error": "Layout Lab source/dist mismatch"}
        return {
            "ok": True,
            "repository": repository,
            "source_head": source_head,
            "remote_head": remote_head,
            "package_manager": package_manager,
            "fresh_clone_build": True,
            "layoutlab_website_owned": True,
            "layout_sha256": dist_sha,
            "home_sha256": home_sha,
            "production_cutover": False,
            "steps": steps,
        }
    finally:
        _run(["rm", "-rf", str(verify_root)], cwd=Path.home(), timeout=30)



# realm_fabric_deployment_fence_v1
_DEPLOYMENT_STATE = Path('/home/ubuntu/agent-data/governance/core-deployment.json')
_DEPLOYMENT_LOCK = Path('/home/ubuntu/agent-data/governance/core-deployment.lock')


def _deployment_state_read() -> dict[str, Any]:
    if not _DEPLOYMENT_STATE.exists():
        return {
            'schema': 'agentos.core-deployment/v1',
            'deployment_generation': 0,
            'desired_core_commit': None,
            'observed_core_commit': None,
            'lease_owner': None,
            'lease_expires_at': None,
            'deployment_status': 'uninitialized',
        }
    data = json.loads(_DEPLOYMENT_STATE.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('invalid Core deployment state')
    return data


def _deployment_state_write(state: dict[str, Any]) -> None:
    _DEPLOYMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _DEPLOYMENT_STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    _share(tmp)
    tmp.replace(_DEPLOYMENT_STATE)
    _share(_DEPLOYMENT_STATE)


def _observed_realm_commit() -> str | None:
    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')
    if not unit.is_file():
        return None
    for raw in unit.read_text(encoding='utf-8').splitlines():
        if not raw.startswith('ExecStart='):
            continue
        value = raw.split('=', 1)[1]
        parts = value.split('/realm-fabric/releases/', 1)
        if len(parts) != 2:
            return None
        commit = parts[1].split('/', 1)[0].strip().lower()
        if len(commit) == 40 and all(c in '0123456789abcdef' for c in commit):
            return commit
    return None


def _claim_realm_fabric_deployment(params: dict[str, Any]) -> dict[str, Any]:
    import fcntl as _df_fcntl
    from datetime import datetime as _df_datetime, timezone as _df_timezone, timedelta as _df_timedelta
    import re as _df_re

    required = {'desired_core_commit', 'lease_owner', 'expected_generation'}
    optional = {'lease_seconds'}
    if set(params) - (required | optional) or not required.issubset(params):
        raise ValueError('unexpected parameters')
    desired = str(params['desired_core_commit']).strip().lower()
    owner = str(params['lease_owner']).strip()
    expected = int(params['expected_generation'])
    lease_seconds = int(params.get('lease_seconds') or 900)
    if not _df_re.fullmatch(r'[0-9a-f]{40}', desired):
        raise ValueError('desired_core_commit must be a 40-hex git commit')
    if not owner or len(owner) > 200:
        raise ValueError('lease_owner required')
    if lease_seconds < 60 or lease_seconds > 3600:
        raise ValueError('lease_seconds out of range')

    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with _DEPLOYMENT_LOCK.open('a+', encoding='utf-8') as lock:
        _df_fcntl.flock(lock.fileno(), _df_fcntl.LOCK_EX)
        state = _deployment_state_read()
        generation = int(state.get('deployment_generation') or 0)
        now = _df_datetime.now(_df_timezone.utc)
        lease_owner = state.get('lease_owner')
        expires_raw = state.get('lease_expires_at')
        active = False
        if lease_owner and expires_raw:
            try:
                active = _df_datetime.fromisoformat(str(expires_raw)) > now
            except ValueError:
                active = False
        if active and lease_owner != owner:
            return {
                'ok': False,
                'deployment_status': 'rejected_lease',
                'desired_core_commit': state.get('desired_core_commit'),
                'observed_core_commit': _observed_realm_commit(),
                'deployment_generation': generation,
                'lease_owner': lease_owner,
                'lease_expires_at': expires_raw,
            }
        if expected != generation:
            return {
                'ok': False,
                'deployment_status': 'rejected_generation',
                'desired_core_commit': state.get('desired_core_commit'),
                'observed_core_commit': _observed_realm_commit(),
                'deployment_generation': generation,
                'lease_owner': lease_owner,
                'lease_expires_at': expires_raw,
            }
        new_generation = generation + 1
        state = {
            'schema': 'agentos.core-deployment/v1',
            'desired_core_commit': desired,
            'observed_core_commit': _observed_realm_commit(),
            'deployment_generation': new_generation,
            'lease_owner': owner,
            'lease_expires_at': (now + _df_timedelta(seconds=lease_seconds)).isoformat(),
            'deployment_status': 'desired',
            'updated_at': now.isoformat(),
        }
        _deployment_state_write(state)
        return {'ok': True, **state}


def _realm_fabric_deployment_status(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({},):
        raise ValueError('unexpected parameters')
    state = _deployment_state_read()
    state['observed_core_commit'] = _observed_realm_commit()
    if state.get('desired_core_commit') and state.get('desired_core_commit') == state.get('observed_core_commit'):
        state['deployment_status'] = 'converged'
    return {'ok': True, **state}

def _install_realm_fabric_release(params: dict[str, Any]) -> dict[str, Any]:
    """Install one exact AgentOS Core commit as the ubuntu Realm Fabric service.

    The request supplies only a 40-hex source commit. Repository, release root,
    service name, bind address, port, and canonical data root are fixed here.
    No arbitrary path, command, shell, unit, or endpoint is accepted.
    """
    import re as _rf_re
    import shutil as _rf_shutil
    import tempfile as _rf_tempfile
    import urllib.request as _rf_urllib

    required = {'source_commit', 'desired_core_commit', 'lease_owner', 'deployment_generation'}
    if set(params) != required:
        raise ValueError('unexpected parameters')
    source_commit = str(params.get('source_commit') or '').strip().lower()
    desired_core_commit = str(params.get('desired_core_commit') or '').strip().lower()
    lease_owner = str(params.get('lease_owner') or '').strip()
    deployment_generation = int(params.get('deployment_generation'))
    if not _rf_re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('source_commit must be a 40-hex git commit')
    if desired_core_commit != source_commit:
        return {'ok': False, 'deployment_status': 'rejected_desired_mismatch', 'source_commit': source_commit, 'desired_core_commit': desired_core_commit}

    import fcntl as _rf_fcntl
    from datetime import datetime as _rf_datetime, timezone as _rf_timezone
    _DEPLOYMENT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    _deployment_guard = _DEPLOYMENT_LOCK.open('a+', encoding='utf-8')
    _rf_fcntl.flock(_deployment_guard.fileno(), _rf_fcntl.LOCK_EX)
    _deployment_state = _deployment_state_read()
    _current_generation = int(_deployment_state.get('deployment_generation') or 0)
    _lease_expires = _deployment_state.get('lease_expires_at')
    try:
        _lease_active = bool(_lease_expires) and _rf_datetime.fromisoformat(str(_lease_expires)) > _rf_datetime.now(_rf_timezone.utc)
    except ValueError:
        _lease_active = False
    if (
        _current_generation != deployment_generation
        or _deployment_state.get('desired_core_commit') != source_commit
        or _deployment_state.get('lease_owner') != lease_owner
        or not _lease_active
    ):
        _deployment_guard.close()
        return {
            'ok': False,
            'deployment_status': 'rejected_fence',
            'source_commit': source_commit,
            'desired_core_commit': _deployment_state.get('desired_core_commit'),
            'observed_core_commit': _observed_realm_commit(),
            'deployment_generation': _current_generation,
            'lease_owner': _deployment_state.get('lease_owner'),
            'lease_expires_at': _deployment_state.get('lease_expires_at'),
        }

    repo = Path('/home/ubuntu/agentmanager')
    if not (repo / '.git').exists():
        return {'ok': False, 'stage': 'source_repo', 'error': 'canonical Core checkout unavailable'}

    realm_root = Path('/home/ubuntu/.local/share/agentos/realm-fabric')
    release = realm_root / 'releases' / source_commit
    current = realm_root / 'current'
    unit = Path('/home/ubuntu/.config/systemd/user/agentos-realm-fabric.service')
    data_root = Path('/home/ubuntu/agent-data')
    previous = current.resolve() if current.is_symlink() else None
    steps: list[dict[str, Any]] = []

    fetch = _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'fetch', 'origin', source_commit], cwd=repo, timeout=120)
    steps.append({'step': 'fetch_source_commit', **fetch})
    if fetch['returncode'] != 0:
        return {'ok': False, 'stage': 'fetch_source_commit', 'source_commit': source_commit, 'steps': steps}

    with _rf_tempfile.TemporaryDirectory(prefix='realm-fabric-release-') as td:
        checkout = Path(td) / 'source'
        wt = _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'add', '--detach', str(checkout), source_commit], cwd=repo, timeout=90)
        steps.append({'step': 'materialize_source', **wt})
        if wt['returncode'] != 0:
            return {'ok': False, 'stage': 'materialize_source', 'source_commit': source_commit, 'steps': steps}
        try:
            release.mkdir(parents=True, exist_ok=True)
            for name in ('agent_core', 'agentos_node', 'runtime_core'):
                src = checkout / name
                dst = release / name
                if dst.exists():
                    _rf_shutil.rmtree(dst)
                if src.is_dir():
                    _rf_shutil.copytree(src, dst)
            bindir = release / 'bin'
            bindir.mkdir(parents=True, exist_ok=True)
            launcher = bindir / 'agentos-one'
            launcher.write_text(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                f'# realm_fabric_release_isolation_v1\ncd {release}\n'
                'export PYTHONNOUSERSITE=1\n'
                f'export PYTHONPATH={release}:"${{PYTHONPATH:-}}"\n'
                'exec /usr/bin/python3 -m agent_core.realm_cli "$@"\n',
                encoding='utf-8',
            )
            launcher.chmod(0o755)

            verify = _run([str(launcher), '--help'], cwd=release, timeout=20)
            steps.append({'step': 'verify_launcher', **verify})
            if verify['returncode'] != 0:
                return {'ok': False, 'stage': 'verify_launcher', 'source_commit': source_commit, 'steps': steps}

            realm_id = 'realm-alston'
            env_file = repo / '.env'
            if env_file.is_file():
                for raw in env_file.read_text(encoding='utf-8').splitlines():
                    if raw.startswith('AGENTOS_REALM_ID=') and raw.split('=', 1)[1].strip():
                        realm_id = raw.split('=', 1)[1].strip()
            init = _run([str(launcher), 'init', '--realm-id', realm_id], cwd=release, timeout=30)
            steps.append({'step': 'init_realm', **init})
            if init['returncode'] != 0:
                return {'ok': False, 'stage': 'init_realm', 'source_commit': source_commit, 'steps': steps}

            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text(
                '[Unit]\nDescription=AgentOS ONE Realm Fabric\nAfter=network.target\n\n'
                '[Service]\nType=simple\n'
                f'Environment=AGENT_DATA_ROOT={data_root}\n'
                'Environment=PYTHONNOUSERSITE=1\n'
                f'WorkingDirectory={release}\n'
                f'ExecStart={launcher} serve --host 127.0.0.1 --port 8780\n'
                'Restart=always\nRestartSec=5\n'
                f'StandardOutput=append:{data_root}/logs/realm-fabric.log\n'
                f'StandardError=append:{data_root}/logs/realm-fabric.log\n\n'
                '[Install]\nWantedBy=default.target\n',
                encoding='utf-8',
            )

            reload_step = _run(['systemctl', '--user', 'daemon-reload'], cwd=Path.home(), timeout=15)
            steps.append({'step': 'daemon_reload', **reload_step})
            if reload_step['returncode'] != 0:
                return {'ok': False, 'stage': 'daemon_reload', 'source_commit': source_commit, 'steps': steps}
            enable = _run(['systemctl', '--user', 'enable', 'agentos-realm-fabric.service'], cwd=Path.home(), timeout=15)
            steps.append({'step': 'enable_service', **enable})
            if enable['returncode'] != 0:
                return {'ok': False, 'stage': 'enable_service', 'source_commit': source_commit, 'steps': steps}
            # realm_fabric_process_attestation_v1
            before_pid_result = _run(['systemctl', '--user', 'show', 'agentos-realm-fabric.service', '--property=MainPID', '--value'], cwd=Path.home(), timeout=10)
            try:
                main_pid_before = int((before_pid_result.get('stdout') or '0').strip() or '0')
            except ValueError:
                main_pid_before = 0
            restart = _restart_user_service('agentos-realm-fabric.service', timeout=25)
            steps.append({'step': 'restart_service', 'main_pid_before': main_pid_before, **restart})
            if not restart.get('ok'):
                if previous and previous.is_dir():
                    current.unlink(missing_ok=True)
                    current.symlink_to(previous)
                return {'ok': False, 'stage': 'restart_service', 'source_commit': source_commit, 'steps': steps}

            main_pid_after = 0
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                pid_result = _run(['systemctl', '--user', 'show', 'agentos-realm-fabric.service', '--property=MainPID', '--value'], cwd=Path.home(), timeout=10)
                try:
                    candidate = int((pid_result.get('stdout') or '0').strip() or '0')
                except ValueError:
                    candidate = 0
                if candidate > 0 and (main_pid_before <= 0 or candidate != main_pid_before):
                    main_pid_after = candidate
                    break
                time.sleep(0.25)
            if main_pid_after <= 0:
                return {'ok': False, 'stage': 'process_identity', 'source_commit': source_commit, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            health = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    with _rf_urllib.urlopen('http://127.0.0.1:8780/v1/health', timeout=2) as resp:
                        body = resp.read().decode('utf-8', 'replace')
                        health = {'status': resp.status, 'body': body[-4000:]}
                        if resp.status == 200:
                            break
                except Exception as exc:
                    health = {'error': type(exc).__name__ + ': ' + str(exc)}
                time.sleep(0.5)
            if not health or health.get('status') != 200:
                return {'ok': False, 'stage': 'health', 'source_commit': source_commit, 'health': health, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            resolve_auth_probe = None
            try:
                req = _rf_urllib.Request(
                    'http://127.0.0.1:8780/v1/resolve',
                    data=json.dumps({'schema':'agentos.resolve-request/v1','node_id':'realm-fabric-deploy-attestation','intent':'continue','project':'agentos-core'}).encode('utf-8'),
                    headers={'Content-Type':'application/json'},
                    method='POST',
                )
                try:
                    with _rf_urllib.urlopen(req, timeout=3) as resp:
                        resolve_auth_probe = {'status': resp.status, 'body': resp.read().decode('utf-8','replace')[-4000:]}
                except _rf_urllib.HTTPError as exc:
                    resolve_auth_probe = {'status': exc.code, 'body': exc.read().decode('utf-8','replace')[-4000:]}
            except Exception as exc:
                resolve_auth_probe = {'error': type(exc).__name__ + ': ' + str(exc)}
            if not resolve_auth_probe or resolve_auth_probe.get('status') != 401:
                return {'ok': False, 'stage': 'resolve_auth_probe', 'source_commit': source_commit, 'health': health, 'resolve_auth_probe': resolve_auth_probe, 'main_pid_before': main_pid_before, 'main_pid_after': main_pid_after, 'steps': steps}

            current_pointer_mode = 'symlink'
            if current.exists() and not current.is_symlink():
                # Preserve the legacy real directory. The systemd unit already
                # points at this exact versioned release, so replacing a live
                # directory just to normalize the pointer would be destructive.
                current_pointer_mode = 'legacy_directory_preserved'
            else:
                tmp_link = realm_root / f'.current-{source_commit}'
                tmp_link.unlink(missing_ok=True)
                tmp_link.symlink_to(release)
                tmp_link.replace(current)
            _deployment_state['observed_core_commit'] = source_commit
            _deployment_state['deployment_status'] = 'converged'
            _deployment_state['updated_at'] = _rf_datetime.now(_rf_timezone.utc).isoformat()
            _deployment_state_write(_deployment_state)
            return {
                'ok': True,
                'deployment_status': 'converged',
                'desired_core_commit': source_commit,
                'observed_core_commit': source_commit,
                'deployment_generation': deployment_generation,
                'lease_owner': lease_owner,
                'lease_expires_at': _deployment_state.get('lease_expires_at'),
                'source_commit': source_commit,
                'realm_id': realm_id,
                'release': str(release),
                'current': str(current),
                'current_pointer_mode': current_pointer_mode,
                'service': 'agentos-realm-fabric.service',
                'endpoint': 'http://127.0.0.1:8780',
                'health': health,
                'resolve_auth_probe': resolve_auth_probe,
                'main_pid_before': main_pid_before,
                'main_pid_after': main_pid_after,
                'process_identity_attested': True,
                'steps': steps,
            }
        finally:
            _run(['git', '-c', f'safe.directory={repo}', '-C', str(repo), 'worktree', 'remove', '--force', str(checkout)], cwd=repo, timeout=30)
            _deployment_guard.close()

def _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "layoutlab-api"}): raise ValueError("unexpected parameters")
    return _restart_user_service("layoutlab-api.service")


def _antigravity_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "agentos-antigravity-relay"}): raise ValueError("unexpected parameters")
    return _restart_user_service("agentos-antigravity-relay.service")


ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "site.sync_build": _site_sync_build,
    "layoutlab.static.deploy": _layoutlab_static_deploy,
    "github.repo.ensure_studio_web": _ensure_studio_web_remote,
    "github.repo.ensure_arcanaforge": _ensure_arcanaforge_remote,
    "github.repo.ensure_layoutlib": _ensure_layoutlib_remote,
    "github.repo.import_layoutlib_v079": _import_layoutlib_v079,
    "github.repo.seed_verify_studio_web": _seed_verify_studio_web_remote,
    "layoutlab.api.restart": _layoutlab_api_restart,
    "agentos.antigravity.restart": _antigravity_restart,
    "agentos.realm-fabric.claim_deployment": _claim_realm_fabric_deployment,
    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,
    "agentos.realm-fabric.install_release": _install_realm_fabric_release,
    "agentos.project.register_core": _register_agentos_core_project,
}


class ActionRelayWorker:
    """Ubuntu-owned deterministic consumer. It never invokes a shell or LLM."""
    def __init__(self, root: str | Path): self.paths = Paths(root)

    def recover_interrupted(self) -> list[str]:
        """Terminalize leftover processing capsules without replaying them.

        A capsule left in processing means a previous worker disappeared after
        taking ownership of execution but before emitting a receipt. The side
        effect outcome is therefore unknown. Replaying would violate the relay's
        at-most-once safety boundary, so preserve the original capsule in
        quarantine and emit an explicit terminal receipt instead.
        """
        self.paths.ensure(); recovered: list[str] = []
        for processing in sorted(self.paths.processing.glob("action-*.json")):
            capsule_id = processing.stem
            target = self.paths.receipts / f"{capsule_id}.json"
            if target.exists():
                quarantine = self.paths.quarantine / processing.name
                processing.replace(quarantine); _share(quarantine); recovered.append(capsule_id)
                continue
            action = None
            try:
                capsule = json.loads(processing.read_text(encoding="utf-8"))
                action = capsule.get("action")
                capsule_id = str(capsule.get("capsule_id") or capsule_id)
            except Exception:
                pass
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "action": action,
                "started_at": None,
                "completed_at": _now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
                "ok": False,
                "outcome": "unknown",
                "replayed": False,
                "error": "interrupted_before_receipt; capsule quarantined and not replayed",
            }
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            _share(tmp); tmp.replace(target); _share(target)
            quarantine = self.paths.quarantine / processing.name
            processing.replace(quarantine); _share(quarantine); recovered.append(capsule_id)
        return recovered

    def process_one(self) -> dict[str, Any] | None:
        self.paths.ensure(); candidates = sorted(self.paths.inbox.glob("action-*.json"))
        if not candidates: return None
        source = candidates[0]; processing = self.paths.processing / source.name; source.replace(processing); _share(processing)
        started = _now(); capsule_id = processing.stem
        try:
            capsule = json.loads(processing.read_text(encoding="utf-8"))
            if capsule.get("schema") != ACTION_SCHEMA: raise ValueError("invalid action schema")
            capsule_id = str(capsule.get("capsule_id") or ""); action = str(capsule.get("action") or ""); params = capsule.get("params")
            if not capsule_id or action not in ACTIONS or not isinstance(params, dict): raise ValueError("invalid action capsule")
            supplied = str(capsule.get("digest") or ""); unsigned = dict(capsule); unsigned.pop("digest", None)
            expected = "sha256:" + hashlib.sha256(_canonical(unsigned)).hexdigest()
            if supplied != expected: raise ValueError("capsule digest mismatch")
            result = ACTIONS[action](params)
            # governed_receipt_reserved_fields_v1: the relay owns receipt identity.
            # Capability results may carry their own schema/metadata but must never
            # overwrite the governance envelope used for validation and audit.
            receipt = {
                "schema": RECEIPT_SCHEMA,
                "capsule_id": capsule_id,
                "action": action,
                "started_at": started,
                "completed_at": _now(),
                "executor_user": os.environ.get("USER") or str(os.getuid()),
            }
            reserved = {"schema", "capsule_id", "action", "started_at", "completed_at", "executor_user"}
            for key, value in result.items():
                receipt[("result_" + key) if key in reserved else key] = value
        except Exception as exc:
            receipt = {"schema": RECEIPT_SCHEMA,"capsule_id": capsule_id,"started_at": started,"completed_at": _now(),"executor_user": os.environ.get("USER") or str(os.getuid()),"ok": False,"error": f"{type(exc).__name__}: {exc}"}
        target = self.paths.receipts / f"{capsule_id}.json"; tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        _share(tmp); tmp.replace(target); _share(target); processing.unlink(missing_ok=True); return receipt

    def serve(self, interval: float = 1.0) -> None:
        self.recover_interrupted()
        while True:
            if self.process_one() is None: time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--once", action="store_true")
    args = p.parse_args(argv); worker = ActionRelayWorker(args.root)
    if args.once:
        recovered = worker.recover_interrupted()
        print(json.dumps(worker.process_one() or {"status":"idle", "recovered": recovered}, indent=2, ensure_ascii=False)); return 0
    worker.serve(); return 0

if __name__ == "__main__": raise SystemExit(main())
