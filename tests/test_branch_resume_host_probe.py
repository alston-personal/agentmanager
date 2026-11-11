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
