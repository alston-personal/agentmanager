from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.rollout_product_employee_runtime as rollout_module
from scripts.rollout_product_employee_runtime import build_request, project_tracked_dirty, rollout


SHA = "a" * 40


class FakeDispatcher:
    def __init__(self, receipt):
        self.receipt = receipt
        self.request = None
        self.task_id = "action-test-1"

    def submit(self, *, request):
        self.request = dict(request)
        return {
            "schema": "agentos.runtime-converge-submission/v1",
            "ok": True,
            "task_id": self.task_id,
            "state": "queued",
        }

    def inspect(self, task_id):
        assert task_id == self.task_id
        return dict(self.receipt)


def _env(**changes):
    value = {
        "GITHUB_REPOSITORY": "alston-personal/agentmanager",
        "GITHUB_REF": "refs/heads/core/integration",
        "GITHUB_SHA": SHA,
    }
    value.update(changes)
    return value


def _receipt(**changes):
    value = {
        "schema": "agentos.runtime-converge-receipt/v1",
        "ok": True,
        "action": "node.runtime.converge",
        "task_id": "action-test-1",
        "request_id": f"product-employee-rollout-{SHA}",
        "node_id": "oracle-core-node",
        "repository": "alston-personal/agentmanager",
        "source_ref": "core/integration",
        "source_commit": SHA,
        "previous_commit": "b" * 40,
        "resulting_commit": SHA,
        "health": "passed",
        "rollback": "not_needed",
        "status": "completed",
        "classification": "CONVERGED",
        "idempotent": False,
        "credential_exposed": False,
    }
    value.update(changes)
    return value


def test_build_request_is_fixed_to_current_core_integration_sha():
    request = build_request(_env())
    assert request == {
        "schema": "agentos.runtime-converge-request/v1",
        "request_id": f"product-employee-rollout-{SHA}",
        "node_id": "oracle-core-node",
        "repository": "alston-personal/agentmanager",
        "source_ref": "core/integration",
        "source_commit": SHA,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"GITHUB_REPOSITORY": "other/repo"},
        {"GITHUB_REF": "refs/heads/main"},
        {"GITHUB_SHA": "main"},
    ],
)
def test_rollout_source_cannot_be_selected_by_caller(changes):
    with pytest.raises(RuntimeError):
        build_request(_env(**changes))


def test_rollout_accepts_only_exact_healthy_sanitized_receipt():
    dispatcher = FakeDispatcher(_receipt())
    seen = []
    result = rollout(_env(), dispatcher=dispatcher, quarantine_func=lambda sha: seen.append(sha) or False, timeout_seconds=1, poll_seconds=0.01)
    assert result["resulting_commit"] == SHA
    assert result["health"] == "passed"
    assert result["credential_exposed"] is False
    assert dispatcher.request["source_commit"] == SHA
    assert seen == [SHA]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed", "ok": False, "classification": "tracked_checkout_dirty"},
        {"credential_exposed": True},
        {"resulting_commit": "c" * 40},
        {"health": "failed"},
    ],
)
def test_rollout_fails_closed_on_untrusted_receipt(changes):
    dispatcher = FakeDispatcher(_receipt(**changes))
    with pytest.raises(RuntimeError):
        rollout(_env(), dispatcher=dispatcher, quarantine_func=lambda sha: False, timeout_seconds=1, poll_seconds=0.01)





def test_quarantine_fetches_and_verifies_exact_target_before_classification(monkeypatch: pytest.MonkeyPatch):
    calls = []
    class Proc:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""
    def fake_git(repo, *args):
        calls.append(args)
        if args == ("fetch", "--no-tags", "origin", "core/integration"):
            return Proc()
        if args == ("rev-parse", "FETCH_HEAD"):
            return Proc(stdout=SHA + "\n")
        raise AssertionError(args)
    monkeypatch.setattr(rollout_module, "_git", fake_git)
    monkeypatch.setattr(rollout_module, "_tracked_status", lambda repo: " M agentos.code-workspace.template\0")
    seen = []
    monkeypatch.setattr(
        rollout_module,
        "_quarantine_allowed_node_local_drift",
        lambda repo, source_commit, status: seen.append((source_commit, status)) or True,
    )
    assert rollout_module.quarantine_known_node_local_drift_before_submit(SHA, repo=Path("/tmp/stable")) is True
    assert calls == [
        ("fetch", "--no-tags", "origin", "core/integration"),
        ("rev-parse", "FETCH_HEAD"),
    ]
    assert seen == [(SHA, " M agentos.code-workspace.template\0")]


def test_quarantine_refuses_fetch_head_mismatch(monkeypatch: pytest.MonkeyPatch):
    class Proc:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""
    def fake_git(repo, *args):
        if args == ("fetch", "--no-tags", "origin", "core/integration"):
            return Proc()
        if args == ("rev-parse", "FETCH_HEAD"):
            return Proc(stdout="b" * 40 + "\n")
        raise AssertionError(args)
    monkeypatch.setattr(rollout_module, "_git", fake_git)
    with pytest.raises(RuntimeError, match="quarantine_source_mismatch"):
        rollout_module.quarantine_known_node_local_drift_before_submit(SHA, repo=Path("/tmp/stable"))


def test_rollout_quarantine_failure_prevents_relay_submit():
    dispatcher = FakeDispatcher(_receipt())
    def fail(_sha):
        raise RuntimeError("node_local_drift_backup_conflict")
    with pytest.raises(RuntimeError, match="node_local_drift_backup_conflict"):
        rollout(_env(), dispatcher=dispatcher, quarantine_func=fail, timeout_seconds=1, poll_seconds=0.01)
    assert dispatcher.request is None


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_dirty_projection_exposes_only_path_status_and_equivalence(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "core/integration")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "AgentOS Test")
    tracked = repo / "scripts" / "safe.py"
    tracked.parent.mkdir()
    tracked.write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    target = _git(repo, "rev-parse", "HEAD")
    tracked.write_text("local secret-like content must never be emitted\n", encoding="utf-8")

    projected = project_tracked_dirty(target, repo=repo)
    assert projected["tracked_dirty_count"] == 1
    assert projected["content_exposed"] is False
    assert projected["credential_exposed"] is False
    assert projected["entries"] == [
        {"status": " M", "path": "scripts/safe.py", "target_equivalent": False}
    ]
    serialized = json.dumps(projected, sort_keys=True)
    assert "local secret-like content" not in serialized
    assert "before" not in serialized


def test_dirty_projection_marks_target_equivalent_partial_rollout(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "core/integration")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "AgentOS Test")
    tracked = repo / "agent_core" / "example.py"
    tracked.parent.mkdir()
    tracked.write_text("old\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "old")
    tracked.write_text("target\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "target")
    target = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "HEAD^", "--", "agent_core/example.py")
    # Convert the index back to HEAD^ while leaving the worktree byte-identical
    # to the target, matching the production partial-rollout shape.
    tracked.write_text("target\n", encoding="utf-8")
    projected = project_tracked_dirty(target, repo=repo)
    assert projected["tracked_dirty_count"] == 1
    assert projected["entries"][0]["path"] == "agent_core/example.py"


def test_workflow_is_push_only_source_guard_and_never_mutates_oracle_runtime():
    text = Path(".github/workflows/product-employee-runtime-rollout.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" not in text
    assert "inputs:" not in text
    assert "core/integration" in text
    assert "scripts.rollout_product_employee_runtime" not in text
    assert "self-hosted" not in text
    assert "node.runtime.converge" not in text
    assert "runtime_mutation=DEFERRED_TO_IMMUTABLE_RELEASE_CONTROLLER" in text
    assert "tests/test_product_employee_worker.py" in text
