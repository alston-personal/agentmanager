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

def _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "layoutlab-api"}): raise ValueError("unexpected parameters")
    return _restart_user_service("layoutlab-api.service")



def _publish_project_continuation(params: dict[str, Any]) -> dict[str, Any]:
    """Publish the canonical AgentOS Core continuation through one narrow action.

    The relay accepts no arbitrary path or shell. Project identity, mutation
    authority, schemas, index generation, and canonical target paths are all
    revalidated by the publisher under the ubuntu execution identity.
    """
    from agent_core.project_continuation_index import publish_project_continuation
    return publish_project_continuation(params)

CLAUDE_LIVENESS_PROBES = frozenset({"auth_status", "headless_print", "restricted_headless_print"})
CLAUDE_LIVENESS_MARKER = "AGENTOS_CLAUDE_LIVENESS_PASS"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _claude_probe_result(
    argv: list[str],
    *,
    command_class: str,
    timeout: float,
    marker: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    stdout = ""
    stderr = ""
    returncode = 124
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=str(Path.home()),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = int(completed.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw_stdout = exc.stdout or ""
        raw_stderr = exc.stderr or ""
        stdout = raw_stdout.decode(errors="replace") if isinstance(raw_stdout, bytes) else str(raw_stdout)
        stderr = raw_stderr.decode(errors="replace") if isinstance(raw_stderr, bytes) else str(raw_stderr)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    lowered = (stdout + "\n" + stderr).lower()
    unsupported = any(
        token in lowered
        for token in (
            "unknown option", "unknown command", "unrecognized option",
            "unrecognized command", "invalid option", "no such command",
        )
    )
    result: dict[str, Any] = {
        "command_class": command_class,
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_ms": elapsed_ms,
        "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
        "stdout_sha256": _sha256_text(stdout),
        "stderr_sha256": _sha256_text(stderr),
        "supported": not unsupported,
    }
    if marker is not None:
        result["expected_marker"] = marker
        result["marker_present"] = marker in stdout
    if command_class == "auth_status":
        if unsupported:
            auth_state = "unsupported"
        elif any(token in lowered for token in ("not logged in", "not authenticated", "unauthenticated", "login required")):
            auth_state = "not_authenticated"
        elif any(token in lowered for token in ("logged in", "authenticated")):
            auth_state = "authenticated"
        elif returncode == 0 and not timed_out:
            auth_state = "status_ok_unclassified"
        else:
            auth_state = "unknown"
        result["auth_state"] = auth_state
    return result


def _claude_liveness_diagnose(params: dict[str, Any]) -> dict[str, Any]:
    if set(params) != {"probe"}:
        raise ValueError("unexpected parameters")
    probe = str(params.get("probe") or "").strip()
    if probe not in CLAUDE_LIVENESS_PROBES:
        raise ValueError("unsupported Claude liveness probe")

    # Import lazily so the deterministic Action Relay stays independent
    # from the model relay except for this explicitly-authorized probe.
    from agentos_node.antigravity_relay_worker import discover_executor

    provider, executor = discover_executor("claude")
    if provider != "claude" or not executor:
        return {
            "ok": True,
            "probe": probe,
            "probe_ok": False,
            "supported": False,
            "classification": "executor_unavailable",
        }

    binary = executor[0]
    version = "unknown"
    parts = Path(binary).parts
    for part in parts:
        prefix = "anthropic.claude-code-"
        suffix = "-linux-arm64"
        if part.startswith(prefix) and part.endswith(suffix):
            version = part[len(prefix):-len(suffix)]
            break

    prompt = f"Return exactly {CLAUDE_LIVENESS_MARKER}. Do not use tools."
    if probe == "auth_status":
        argv = [binary, "auth", "status"]
        result = _claude_probe_result(argv, command_class=probe, timeout=20.0)
        probe_ok = result["returncode"] == 0 and not result["timed_out"] and result.get("auth_state") != "not_authenticated"
    else:
        fixed = [binary]
        if probe == "restricted_headless_print":
            fixed.append("--restricted")
        fixed.extend(["--bare", "--print", "--output-format", "text", "--effort", "low", prompt])
        result = _claude_probe_result(
            fixed,
            command_class=probe,
            timeout=30.0,
            marker=CLAUDE_LIVENESS_MARKER,
        )
        probe_ok = (
            result["returncode"] == 0
            and not result["timed_out"]
            and result.get("marker_present") is True
        )

    # `ok` means the bounded diagnostic action itself completed and
    # emitted sanitized evidence. Probe health is carried separately.
    return {
        "ok": True,
        "probe": probe,
        "probe_ok": bool(probe_ok),
        "provider": "claude",
        "executor_version": version,
        "result": result,
        "raw_output_persisted": False,
        "arbitrary_argv": False,
    }


def _antigravity_restart(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({}, {"service": "agentos-antigravity-relay"}): raise ValueError("unexpected parameters")
    return _restart_user_service("agentos-antigravity-relay.service")


ACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "site.sync_build": _site_sync_build,
    "layoutlab.static.deploy": _layoutlab_static_deploy,
    "github.repo.ensure_studio_web": _ensure_studio_web_remote,
    "github.repo.seed_verify_studio_web": _seed_verify_studio_web_remote,
    "layoutlab.api.restart": _layoutlab_api_restart,
    "agentos.antigravity.restart": _antigravity_restart,
    "agentos.claude.liveness_diagnose": _claude_liveness_diagnose,
    "agentos.project.publish_continuation": _publish_project_continuation,
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
            receipt = {"schema": RECEIPT_SCHEMA,"capsule_id": capsule_id,"action": action,"started_at": started,"completed_at": _now(),"executor_user": os.environ.get("USER") or str(os.getuid()),**result}
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
