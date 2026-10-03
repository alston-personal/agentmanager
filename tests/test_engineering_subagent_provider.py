from __future__ import annotations

from pathlib import Path

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node.engineering_subagent_provider import (
    EXECUTOR_CLASS,
    JOBS,
    register_engineering_subagent_providers,
    run_engineering_subagent,
)
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry


class FakeRelay:
    def __init__(self, root):
        self.root = root


def test_engineering_job_contracts_are_fixed_and_bounded():
    expected = {
        "engineering.subagent.smoke": "surface://engineering-subagent",
        "engineering.windows-thin-client.fix": "issue://892",
        "engineering.realm-device-flow.fix": "issue://893",
        "engineering.realm-node-fabric.fix": "issue://894",
    }
    for job_type, workload_ref in expected.items():
        request = canonical_executor_job_request(job_type)
        spec = validate_executor_job(request)
        assert spec.executor_class == EXECUTOR_CLASS
        assert spec.workload_ref == workload_ref
        assert spec.authority == "bounded-code-fix"


def test_provider_registration_covers_all_engineering_jobs(tmp_path: Path):
    registry = ExecutorJobProviderRegistry()
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    assert register_engineering_subagent_providers(
        registry=registry,
        relay_root=tmp_path / "relay",
        workspace=workspace,
    )
    assert set(JOBS).issubset({job for job in JOBS if registry.get(job) is not None})


def test_missing_workspace_fails_closed(tmp_path: Path):
    request = canonical_executor_job_request("engineering.windows-thin-client.fix")
    result = run_engineering_subagent(
        request,
        relay_root=tmp_path / "relay",
        workspace=tmp_path / "missing",
        timeout_seconds=0.01,
    )
    assert result["successful"] is False
    assert result["classification"] == "ENGINEERING_WORKSPACE_UNAVAILABLE"
    assert result["credential_exposed"] is False


def test_engineering_smoke_is_read_only():
    request = canonical_executor_job_request("engineering.subagent.smoke")
    spec = validate_executor_job(request)
    assert spec.read_only is True
    assert spec.authority == "bounded-read-only"
    assert spec.capability == "agentos.engineering.probe"


def test_failed_engineering_job_projects_only_safe_executor_diagnostics(tmp_path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    class FakeClient:
        def __init__(self, root):
            pass
        def submit(self, **kwargs):
            return {"capsule_id": "relay-test"}
        def receipt(self, capsule_id):
            return {
                "schema": "agentos.antigravity-receipt/v1",
                "ok": False,
                "provider": "claude",
                "returncode": 7,
                "timed_out": False,
                "stdout": "private output",
                "stderr": "private error",
            }

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    monkeypatch.setattr(provider, "AntigravityRelayClient", FakeClient)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.subagent.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=0.1,
    )
    assert result["classification"] == "ENGINEERING_EXECUTOR_NONZERO"
    assert result["executor_provider"] == "claude"
    assert result["executor_returncode"] == 7
    assert result["executor_timed_out"] is False
    assert "stdout" not in result
    assert "stderr" not in result


def test_relay_failure_classification_is_bounded():
    from agentos_node.engineering_subagent_provider import _relay_failure_classification

    assert _relay_failure_classification({"ok": False, "timed_out": True, "returncode": 124}) == "ENGINEERING_EXECUTOR_TIMEOUT"
    assert _relay_failure_classification({
        "ok": False,
        "error": "RuntimeError: no authorized local Antigravity executor discovered for provider=claude",
    }) == "ENGINEERING_EXECUTOR_UNAVAILABLE"
    assert _relay_failure_classification({"ok": False, "returncode": 7}) == "ENGINEERING_EXECUTOR_NONZERO"
    assert _relay_failure_classification({"ok": False, "error": "RuntimeError: bounded failure"}) == "ENGINEERING_EXECUTOR_RUNTIME_ERROR"


def test_read_only_smoke_is_deterministic_and_does_not_require_model(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    import subprocess
    subprocess.run(["git", "init", str(workspace)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(workspace), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(workspace), "config", "user.name", "Test"], check=True)
    (workspace / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workspace), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(workspace), "commit", "-m", "init"], check=True, capture_output=True)
    request = canonical_executor_job_request("engineering.subagent.smoke")
    result = run_engineering_subagent(
        request,
        relay_root=tmp_path / "unused-relay",
        workspace=workspace,
        timeout_seconds=0.01,
    )
    assert result["classification"] == "ENGINEERING_SUBAGENT_SMOKE_COMPLETED_PENDING_VERIFICATION"
    assert result["executor_provider"] == "deterministic-git-probe"
    assert result["executor_returncode"] == 0
    assert result["executor_timed_out"] is False
    assert result["worktree_clean"] is True
    assert len(result["observed_head"]) == 40
    assert result["successful"] is False
