#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

OVERLAY_COMMIT = "f842bee2cf7c24fc3bf7424bd121994562e829cd"
EXPECTED_GENERATION = 6
EXPECTED_OWNER = "agentos-core-mainline"
REPO = Path("/home/ubuntu/agentmanager")
RUNTIME = Path("/home/ubuntu/.local/share/agentos/action-relay-runtime")
UNIT = "agentos-action-relay.service"
STATE = Path("/home/ubuntu/agent-data/governance/core-deployment.json")
BACKUP_ROOT = Path("/home/ubuntu/.local/state/agentos/action-relay-overlays")


def run(argv: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(argv, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}: {argv!r}\nstdout={p.stdout[-4000:]}\nstderr={p.stderr[-4000:]}")
    return p


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git_show(commit: str, path: str) -> bytes:
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"], capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"git show failed for {commit}:{path}: {p.stderr.decode('utf-8','replace')[-3000:]}")
    return p.stdout


def assert_live_core_authority() -> dict:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    assert int(state.get("deployment_generation") or 0) == EXPECTED_GENERATION, state
    assert state.get("desired_core_commit") == OVERLAY_COMMIT, state
    assert state.get("observed_core_commit") == OVERLAY_COMMIT, state
    assert state.get("deployment_status") == "converged", state
    assert state.get("lease_status") == "released", state
    assert state.get("lease_owner") == EXPECTED_OWNER, state
    return state


def patch_action_relay(original: str) -> str:
    marker = 'agentos.project.publish_continuation'
    if marker in original:
        raise ValueError("publisher action already present; refuse ambiguous overlay stacking")
    function_anchor = "\nACTIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {\n"
    if function_anchor not in original:
        raise ValueError("canonical ACTIONS anchor missing")
    fn = '''\n\ndef _publish_project_continuation(params: dict[str, Any]) -> dict[str, Any]:\n    from agent_core.project_continuation_index import publish_project_continuation\n    return publish_project_continuation(params)\n'''
    patched = original.replace(function_anchor, fn + function_anchor, 1)
    mapping_anchor = function_anchor
    patched = patched.replace(mapping_anchor, mapping_anchor + '    "agentos.project.publish_continuation": _publish_project_continuation,\n', 1)
    if patched.count(marker) != 1:
        raise ValueError("publisher overlay marker count is not exactly one")
    return patched


def stable_restart() -> None:
    run(["systemctl", "--user", "restart", UNIT], timeout=30)
    stable = 0
    for _ in range(20):
        p = run(["systemctl", "--user", "is-active", "--quiet", UNIT], check=False, timeout=10)
        if p.returncode == 0:
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
        time.sleep(1)
    status = run(["systemctl", "--user", "--no-pager", "--full", "status", UNIT], check=False, timeout=20)
    raise RuntimeError("Action Relay failed stable restart: " + status.stdout[-5000:] + status.stderr[-3000:])


def verify_runtime_actions() -> list[str]:
    code = "from agentos_node.action_relay import ACTIONS; print('\\n'.join(sorted(ACTIONS)))"
    p = run(["python3", "-c", code], cwd=RUNTIME, timeout=30)
    actions = [x.strip() for x in p.stdout.splitlines() if x.strip()]
    required = {
        "agentos.realm-fabric.advance_deployment",
        "agentos.realm-fabric.install_release",
        "agentos.realm-fabric.release_deployment",
        "agentos.project.publish_continuation",
    }
    missing = sorted(required - set(actions))
    if missing:
        raise RuntimeError(f"required governed actions missing after overlay: {missing}; actions={actions}")
    return actions


def main() -> int:
    if os.getuid() != 1001 or (os.environ.get("USER") or "") != "ubuntu":
        raise SystemExit("ERROR: overlay installer must execute as ubuntu uid 1001")
    state = assert_live_core_authority()
    if not (RUNTIME / ".git").exists():
        raise SystemExit(f"ERROR: canonical Action Relay runtime is not a git worktree: {RUNTIME}")
    if run(["git", "status", "--porcelain"], cwd=RUNTIME).stdout.strip():
        raise SystemExit("ERROR: canonical Action Relay runtime is dirty before overlay")

    base_commit = run(["git", "rev-parse", "HEAD"], cwd=RUNTIME).stdout.strip()
    action_path = RUNTIME / "agentos_node" / "action_relay.py"
    module_path = RUNTIME / "agent_core" / "project_continuation_index.py"
    original = action_path.read_bytes()
    original_text = original.decode("utf-8")
    for required in (
        "agentos.realm-fabric.advance_deployment",
        "agentos.realm-fabric.install_release",
        "agentos.realm-fabric.release_deployment",
        "realm_fabric_advance_active_lease_fence_v1",
    ):
        if required not in original_text:
            raise SystemExit(f"ERROR: live base Action Relay lacks governance marker: {required}")

    run(["git", "-C", str(REPO), "fetch", "origin", OVERLAY_COMMIT], timeout=120)
    overlay_module = git_show(OVERLAY_COMMIT, "agent_core/project_continuation_index.py")
    overlay_action = git_show(OVERLAY_COMMIT, "agentos_node/action_relay.py").decode("utf-8")
    if "agentos.project.publish_continuation" not in overlay_action:
        raise SystemExit("ERROR: accepted generation 6 source lacks publisher mapping")
    if b"agentos.project-continuation-publish/v1" not in overlay_module:
        raise SystemExit("ERROR: accepted generation 6 source lacks publisher schema")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_ROOT / f"{stamp}-{OVERLAY_COMMIT[:12]}"
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(action_path, backup / "action_relay.py")
    module_existed = module_path.exists()
    if module_existed:
        shutil.copy2(module_path, backup / "project_continuation_index.py")

    patched = patch_action_relay(original_text).encode("utf-8")
    rolled_back = False
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".action_relay.", suffix=".tmp", dir=str(action_path.parent))
        try:
            os.fchmod(fd, 0o640)
            with os.fdopen(fd, "wb") as f:
                f.write(patched); f.flush(); os.fsync(f.fileno())
            os.replace(tmp_name, action_path)
        finally:
            if os.path.exists(tmp_name): os.unlink(tmp_name)

        module_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".project_continuation_index.", suffix=".tmp", dir=str(module_path.parent))
        try:
            os.fchmod(fd, 0o640)
            with os.fdopen(fd, "wb") as f:
                f.write(overlay_module); f.flush(); os.fsync(f.fileno())
            os.replace(tmp_name, module_path)
        finally:
            if os.path.exists(tmp_name): os.unlink(tmp_name)

        run(["python3", "-m", "py_compile", str(action_path), str(module_path)], cwd=RUNTIME, timeout=30)
        code = (
            "from agent_core.resolve_facade import resolve_project_identity; "
            "p=resolve_project_identity('agentos-core'); "
            "assert p.get('identity_source')=='governance-directory',p; "
            "assert (p.get('integrity') or {}).get('mutation_allowed') is True,p; "
            "print('publisher_identity_authority=PASS')"
        )
        run(["python3", "-c", code], cwd=RUNTIME, timeout=30)
        stable_restart()
        actions = verify_runtime_actions()
    except BaseException:
        shutil.copy2(backup / "action_relay.py", action_path)
        if module_existed:
            shutil.copy2(backup / "project_continuation_index.py", module_path)
        else:
            module_path.unlink(missing_ok=True)
        stable_restart()
        rolled_back = True
        raise

    receipt = {
        "schema": "agentos.action-relay-continuation-overlay/v1",
        "ok": True,
        "executor_user": os.environ.get("USER"),
        "executor_uid": os.getuid(),
        "live_core_generation": EXPECTED_GENERATION,
        "live_core_commit": OVERLAY_COMMIT,
        "base_runtime_commit": base_commit,
        "overlay_source_commit": OVERLAY_COMMIT,
        "base_action_relay_sha256": sha256_bytes(original),
        "patched_action_relay_sha256": sha256_bytes(patched),
        "publisher_module_sha256": sha256_bytes(overlay_module),
        "backup_path": str(backup),
        "runtime_root": str(RUNTIME),
        "service": UNIT,
        "service_active": True,
        "required_governance_actions_preserved": True,
        "publisher_action": "agentos.project.publish_continuation",
        "action_count": len(actions),
        "deployment_state": {
            "deployment_generation": state.get("deployment_generation"),
            "desired_core_commit": state.get("desired_core_commit"),
            "observed_core_commit": state.get("observed_core_commit"),
            "deployment_status": state.get("deployment_status"),
            "lease_status": state.get("lease_status"),
        },
        "rolled_back": rolled_back,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    print("action_relay_continuation_overlay=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
