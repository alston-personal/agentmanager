"""Use real local Git checkouts, not synthetic status-only proof."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentos_node.branch_resume_host_probe import LocalCodeResumeProbe
from agent_core.controller_service import ControllerService
from agent_core.executor_job_contract import JOB_TYPES
from tests.test_branch_resume_controller import dispatch
from tests.test_executor_job_controller_route import FakeDispatcher, _fabric
from scripts.branch_resume_guard import FreshnessError

SPEC = JOB_TYPES["engineering.realm-device-flow.fix"]


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *map(str, args)], cwd=cwd, check=True,
        text=True, capture_output=True,
    ).stdout.strip()


def put_commit(root, filename, content):
    (root / filename).write_text(content, encoding="utf-8")
    git("add", filename, cwd=root)
    git("commit", "-qm", "test fixture", cwd=root)


@pytest.fixture
def checkouts(tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", "-q", "--initial-branch=main", remote)
    writer = tmp_path / "writer"
    git("clone", "-q", remote, writer)
    for key in ("user.name", "user.email"):
        git("config", key, "CI" if key.endswith("name") else "ci@example.invalid", cwd=writer)
    put_commit(writer, "base.txt", "initial")
    git("push", "-q", "origin", "main", cwd=writer)
    worker = tmp_path / "worker"
    git("clone", "-q", remote, worker)
    for key in ("user.name", "user.email"):
        git("config", key, "CI" if key.endswith("name") else "ci@example.invalid", cwd=worker)
    git("checkout", "-qb", "work", cwd=worker)
    put_commit(worker, "work.txt", "worker change")
    return remote, writer, worker


def provider(remote, worker):
    return LocalCodeResumeProbe(
        worktrees={SPEC.job_type: worker},
        origin_url=str(remote),
    )


def test_git_provider_accepts_current_and_denies_remote_advanced(checkouts):
    remote, writer, worker = checkouts
    probe = provider(remote, worker)
    fresh = probe(SPEC)
    assert fresh["status"] == "MAINLINE_CURRENT"
    assert fresh["allowed"] is True
    assert fresh["work_sha"] == git("rev-parse", "HEAD", cwd=worker)
    put_commit(writer, "main-advance.txt", "important new auth system")
    git("push", "-q", "origin", "main", cwd=writer)
    stale = probe(SPEC)
    assert stale["status"] == "RECONCILE_REQUIRED"
    assert stale["allowed"] is False
    assert stale["main_sha"] == git("rev-parse", "HEAD", cwd=writer)


def test_origin_mismatch_and_dirty_worktree_fail_closed(checkouts):
    remote, _, worker = checkouts
    with pytest.raises(FreshnessError, match="UNTRUSTED_WORKTREE_ORIGIN"):
        LocalCodeResumeProbe(
            worktrees={SPEC.job_type: worker},
            origin_url=str(remote) + "-incorrect",
        )(SPEC)
    (worker / "uncommitted.txt").write_text("uncommitted")
    with pytest.raises(FreshnessError, match="WORKTREE_DIRTY"):
        provider(remote, worker)(SPEC)


def test_registered_worktree_required_and_uncertainty_denied(checkouts):
    remote, _, worker = checkouts
    with pytest.raises(FreshnessError, match="WORKTREE_NOT_REGISTERED"):
        LocalCodeResumeProbe(
            worktrees={"engineering.other.fix": worker},
            origin_url=str(remote),
        )(SPEC)
    with pytest.raises(FreshnessError, match="NOT_A_CODE_FIX_JOB"):
        provider(remote, worker)(JOB_TYPES["experience.regression"])


def test_actual_one_controller_blocks_stale_worktree_before_executor(checkouts, tmp_path):
    remote, writer, worker = checkouts
    target = FakeDispatcher()
    controller = ControllerService(
        _fabric(tmp_path), executor_job_dispatcher=target,
        code_resume_probe=provider(remote, worker),
    )
    first = dispatch(controller)
    assert first["job_id"] == "action-12345678"
    assert len(target.calls) == 1
    put_commit(writer, "main-advance.txt", "OAuth update")
    git("push", "-q", "origin", "main", cwd=writer)
    with pytest.raises(ValueError, match="CODE_MAINLINE_RECONCILE_REQUIRED"):
        dispatch(controller)
    assert len(target.calls) == 1


def test_corrupted_origin_fails_at_one_dispatch_not_with_fake_permission(checkouts, tmp_path):
    remote, _, worker = checkouts
    controller = ControllerService(
        _fabric(tmp_path), executor_job_dispatcher=FakeDispatcher(),
        code_resume_probe=LocalCodeResumeProbe(
            worktrees={SPEC.job_type: worker}, origin_url="untrusted",
        ),
    )
    with pytest.raises(ValueError, match="CODE_MAINLINE_EVIDENCE_UNAVAILABLE"):
        dispatch(controller)


def test_operator_config_binds_server_owned_probe_and_rejects_world_readable(checkouts, tmp_path, monkeypatch):
    import json
    import os
    from agentos_node.branch_resume_host_probe import load_trusted_code_resume_probe
    from agent_core.realm_server import RealmHTTPServer
    remote, _, worker = checkouts
    cfg = tmp_path / "code-resume-host.json"
    cfg.write_text(json.dumps({
        "schema": "agentos.branch-resume-host/v1",
        "origin_url": str(remote),
        "worktrees": {SPEC.job_type: str(worker)},
    }), encoding="utf-8")
    cfg.chmod(0o600)
    assert load_trusted_code_resume_probe(None) is None
    assert load_trusted_code_resume_probe(str(cfg))(SPEC)["status"] == "MAINLINE_CURRENT"
    monkeypatch.setenv("AGENTOS_CODE_RESUME_HOST_CONFIG", str(cfg))
    server = RealmHTTPServer(("127.0.0.1", 0), _fabric(tmp_path))
    try:
        assert server.code_resume_probe(SPEC)["status"] == "MAINLINE_CURRENT"
    finally:
        server.server_close()
    cfg.chmod(0o644)
    with pytest.raises(FreshnessError, match="UNTRUSTED_HOST_CONFIG_PERMISSIONS"):
        load_trusted_code_resume_probe(str(cfg))
    cfg.chmod(0o600)
    symlink = tmp_path / "config-link.json"
    symlink.symlink_to(cfg)
    with pytest.raises(FreshnessError, match="UNTRUSTED_HOST_CONFIG_PATH"):
        load_trusted_code_resume_probe(str(symlink))


def test_host_config_rejects_untrusted_schema(checkouts, tmp_path):
    import json
    from agentos_node.branch_resume_host_probe import load_trusted_code_resume_probe
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({
        "schema": "agentos.branch-resume-host/v1",
        "origin_url": "unused",
        "worktrees": {},
        "token": "not allowed",
    }))
    cfg.chmod(0o600)
    with pytest.raises(FreshnessError, match="INVALID_HOST_CONFIG"):
        load_trusted_code_resume_probe(str(cfg))



def test_mainline_action_relay_imports_and_legacy_authority_is_refused():
    """Canonical Action Relay may load; removed deploy powers must not revive."""
    from agentos_node import action_relay
    from agentos_node import executor_job_action_relay
    assert action_relay.ACTIONS["agentos.executor.job"] is executor_job_action_relay._execute
    for key in (
        "agentos.realm-fabric.claim_deployment",
        "agentos.realm-fabric.deployment_status",
        "agentos.realm-fabric.release_deployment",
        "agentos.realm-fabric.renew_deployment",
        "agentos.realm-fabric.advance_deployment",
        "agentos.realm-fabric.install_release",
    ):
        with pytest.raises(ValueError, match="LEGACY_ACTION_REQUIRES_CONVERGENCE"):
            action_relay.ACTIONS[key]({})
    assert action_relay.ACTIONS["github.actions.workflow.dispatch"] is action_relay._github_actions_dispatch


def _load_real_worker_function_in_isolation():
    """Test the actual worker function body while baseline Action Relay import is broken.

    Main's ACTIONS registry has unresolved legacy Realm Fabric entries; do not
    fake a successful full module import or port broad deployment code here.
    """
    import ast
    import os
    from agent_core.code_resume_authority import require_fresh_code_resume
    from agent_core.executor_job_contract import validate_executor_job
    from agentos_node.branch_resume_host_probe import load_trusted_code_resume_probe

    path = Path(__file__).resolve().parents[1] / "agentos_node" / "executor_job_action_relay.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fn = next(node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "_execute")
    code = compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec")
    scope = {
        "os": os,
        "validate_executor_job": validate_executor_job,
        "require_fresh_code_resume": require_fresh_code_resume,
        "load_trusted_code_resume_probe": load_trusted_code_resume_probe,
        "_request_projection": lambda request: dict(request),
        "run_registered_executor_job": lambda *, request: {"ok": True},
    }
    exec(code, scope)
    return scope, scope["_execute"]


def test_queued_executor_rechecks_main_just_before_mutating(checkouts):
    from tests.test_branch_resume_controller import request
    remote, writer, checkout = checkouts
    scope, execute = _load_real_worker_function_in_isolation()
    executed = []
    scope["load_trusted_code_resume_probe"] = lambda path: provider(remote, checkout)
    scope["run_registered_executor_job"] = (
        lambda *, request: executed.append(request["job_type"]) or {"ok": True}
    )
    packet = {"request": request()}
    assert execute(packet)["ok"] is True
    assert executed == [SPEC.job_type]
    put_commit(writer, "another-main-update.txt", "new feature from a second agent")
    git("push", "-q", "origin", "main", cwd=writer)
    with pytest.raises(ValueError, match="CODE_MAINLINE_RECONCILE_REQUIRED"):
        execute(packet)
    assert executed == [SPEC.job_type]


def test_worker_code_job_does_not_execute_without_host_configuration(monkeypatch):
    from tests.test_branch_resume_controller import request
    scope, execute = _load_real_worker_function_in_isolation()
    monkeypatch.delenv("AGENTOS_CODE_RESUME_HOST_CONFIG", raising=False)
    calls = []
    scope["run_registered_executor_job"] = (
        lambda *, request: calls.append(request) or {"ok": True}
    )
    with pytest.raises(ValueError, match="CODE_MAINLINE_PROBE_UNAVAILABLE"):
        execute({"request": request()})
    assert calls == []
