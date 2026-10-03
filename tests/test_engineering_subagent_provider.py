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
        "engineering.subagent.smoke": ("surface://engineering-subagent", "bounded-read-only", True),
        "engineering.executor.health": ("surface://engineering-executors", "bounded-read-only", True),
        "engineering.model.smoke": ("surface://engineering-model-subagent", "bounded-read-only", True),
        "engineering.windows-thin-client.fix": ("issue://892", "bounded-code-fix", False),
        "engineering.realm-device-flow.fix": ("issue://893", "bounded-code-fix", False),
        "engineering.realm-node-fabric.fix": ("issue://894", "bounded-code-fix", False),
    }
    for job_type, (workload_ref, authority, read_only) in expected.items():
        request = canonical_executor_job_request(job_type)
        spec = validate_executor_job(request)
        assert spec.executor_class == EXECUTOR_CLASS
        assert spec.workload_ref == workload_ref
        assert spec.authority == authority
        assert spec.read_only is read_only


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
    monkeypatch.setattr(
        provider,
        "_read_executor_health",
        lambda: {
            "verdict": "PASS",
            "classification": "ENGINEERING_EXECUTOR_HEALTH_READY",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "selected_provider": "claude",
        },
    )
    monkeypatch.setattr(provider, "AntigravityRelayClient", FakeClient)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.windows-thin-client.fix"),
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


def _snapshot_row(executor_id: str, *, state: str, stable: bool, streak: int, classification: str = ""):
    return {
        "executor_id": executor_id,
        "provider_id": "anthropic" if executor_id == "claude-code" else "google-antigravity",
        "executor_class": executor_id,
        "state": state,
        "adopted": True,
        "routable": state == "READY",
        "stable_routable": stable,
        "ready_streak": streak,
        "profile_valid": True,
        "adapter_registered": True,
        "discovered": True,
        "reachable": True,
        "authorized": state == "READY",
        "healthy": state == "READY",
        "provider_health": {"classification": classification} if classification else {},
        "capabilities": ["agent.chat", "code.edit"],
    }


def test_snapshot_health_selects_only_stable_ready_provider(monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    snapshot = {
        "schema": "agentos.executor-adoption/v0.2",
        "observed_at": "2026-10-03T07:00:00Z",
        "executors": [
            _snapshot_row("claude-code", state="UNHEALTHY", stable=False, streak=0, classification="TIMEOUT"),
            _snapshot_row("antigravity", state="READY", stable=True, streak=2),
        ],
    }
    result = provider._health_from_snapshot(snapshot)
    assert result["classification"] == "ENGINEERING_EXECUTOR_HEALTH_READY"
    assert result["selected_provider"] == "agy"
    assert result["claude_state"] == "TIMEOUT"
    assert result["agy_state"] == "READY"
    assert result["agy_ready_count"] == 2
    assert result["successful"] is True


def test_snapshot_health_treats_first_ready_sample_as_flaky(monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    snapshot = {
        "schema": "agentos.executor-adoption/v0.2",
        "observed_at": "2026-10-03T07:00:00Z",
        "executors": [
            _snapshot_row("claude-code", state="UNHEALTHY", stable=False, streak=0, classification="TIMEOUT"),
            _snapshot_row("antigravity", state="READY", stable=False, streak=1),
        ],
    }
    result = provider._health_from_snapshot(snapshot)
    assert result["agy_state"] == "FLAKY"
    assert result["agy_ready_count"] == 1
    assert result["selected_provider"] == ""
    assert result["successful"] is False


def test_model_job_fails_closed_on_stale_health_snapshot(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    monkeypatch.setattr(provider, "_load_executor_snapshot", lambda **kwargs: None)

    class FailIfConstructed:
        def __init__(self, root):
            raise AssertionError("relay must not be touched with stale health")

    monkeypatch.setattr(provider, "AntigravityRelayClient", FailIfConstructed)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.model.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=1,
    )
    assert result["classification"] == "ENGINEERING_EXECUTOR_HEALTH_SNAPSHOT_STALE"
    assert result["routable"] is False



def test_claude_health_probe_uses_safe_single_turn_no_tool_mode(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    captured = {}
    monkeypatch.setattr(provider, "discover_executor", lambda name: ("claude", ["/fake/claude", "--print", "--output-format", "text", "--effort", "low"]))

    class Completed:
        returncode = 0
        stdout = "READY"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return Completed()

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    result = provider._probe_model_provider("claude", workspace, timeout_seconds=1)

    argv = captured["argv"]
    assert "--safe-mode" in argv
    assert "--tools" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert "--disallowedTools" in argv
    assert argv[argv.index("--disallowedTools") + 1] == "mcp__*"
    assert "--max-turns" in argv
    assert argv[argv.index("--max-turns") + 1] == "1"
    assert "--disable-slash-commands" in argv
    assert result["state"] == "READY"
    assert result["timed_out"] is False


def test_model_smoke_routes_through_health_selected_provider(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    monkeypatch.setattr(
        provider,
        "_read_executor_health",
        lambda: {
            "verdict": "PASS",
            "classification": "ENGINEERING_EXECUTOR_HEALTH_READY",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "selected_provider": "agy",
        },
    )

    submitted = {}
    class FakeClient:
        def __init__(self, root):
            self.root = root
        def submit(self, **kwargs):
            submitted.update(kwargs)
            return {"capsule_id": "relay-test"}
        def receipt(self, capsule_id):
            assert capsule_id == "relay-test"
            return {
                "ok": True,
                "provider": "agy",
                "returncode": 0,
                "timed_out": False,
            }

    monkeypatch.setattr(provider, "AntigravityRelayClient", FakeClient)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.model.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=1,
    )

    assert submitted["executor_hint"] == "provider:agy"
    assert result["classification"] == "ENGINEERING_MODEL_SMOKE_COMPLETED_PENDING_VERIFICATION"
    assert result["executor_provider"] == "agy"
    assert result["executor_returncode"] == 0
    assert result["executor_timed_out"] is False
    assert result["successful"] is False


def test_engineering_job_fails_before_relay_when_no_provider_is_healthy(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    health = {
        "verdict": "FAIL",
        "classification": "ENGINEERING_EXECUTOR_NO_HEALTHY_PROVIDER",
        "executor_available": True,
        "routable": False,
        "authorized": False,
        "successful": False,
        "credential_exposed": False,
        "selected_provider": "",
    }
    monkeypatch.setattr(provider, "_read_executor_health", lambda: dict(health))

    class FailIfConstructed:
        def __init__(self, root):
            raise AssertionError("relay must not be touched without a healthy provider")

    monkeypatch.setattr(provider, "AntigravityRelayClient", FailIfConstructed)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.model.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=1,
    )
    assert result["classification"] == "ENGINEERING_EXECUTOR_NO_HEALTHY_PROVIDER"
    assert result["routable"] is False


def test_timeout_with_auth_evidence_classifies_auth_required():
    from agentos_node.engineering_subagent_provider import _classify_probe_output
    assert _classify_probe_output(124, "Please login to continue", timed_out=True) == "AUTH_REQUIRED"


def test_model_smoke_uses_minimal_read_only_capsule(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    monkeypatch.setattr(
        provider,
        "_read_executor_health",
        lambda: {
            "verdict": "PASS",
            "classification": "ENGINEERING_EXECUTOR_HEALTH_READY",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "selected_provider": "agy",
        },
    )

    submitted = {}
    class FakeClient:
        def __init__(self, root):
            self.root = root
        def submit(self, **kwargs):
            submitted.update(kwargs)
            return {"capsule_id": "relay-minimal"}
        def receipt(self, capsule_id):
            return {"ok": True, "provider": "agy", "returncode": 0, "timed_out": False}

    monkeypatch.setattr(provider, "AntigravityRelayClient", FakeClient)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.model.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=1,
    )

    assert submitted["canonical_ir"] == {"schema": "agentos.engineering-subagent-ir/v1"}
    assert submitted["instruction"] == "AgentOS routed model smoke. Do not modify files. Reply exactly READY."
    assert submitted["executor_hint"] == "provider:agy"
    assert result["selected_provider"] == "agy"
    assert result["executor_provider"] == "agy"


def test_model_failure_preserves_selected_provider_when_relay_receipt_omits_provider(tmp_path: Path, monkeypatch):
    import agentos_node.engineering_subagent_provider as provider

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()

    monkeypatch.setattr(
        provider,
        "_read_executor_health",
        lambda: {
            "verdict": "PASS",
            "classification": "ENGINEERING_EXECUTOR_HEALTH_READY",
            "executor_available": True,
            "routable": True,
            "authorized": True,
            "successful": True,
            "credential_exposed": False,
            "selected_provider": "agy",
        },
    )

    class FakeClient:
        def __init__(self, root):
            self.root = root
        def submit(self, **kwargs):
            return {"capsule_id": "relay-timeout"}
        def receipt(self, capsule_id):
            return {"ok": False, "returncode": 124, "timed_out": True}

    monkeypatch.setattr(provider, "AntigravityRelayClient", FakeClient)
    result = provider.run_engineering_subagent(
        canonical_executor_job_request("engineering.model.smoke"),
        relay_root=tmp_path / "relay",
        workspace=workspace,
        timeout_seconds=1,
    )

    assert result["classification"] == "ENGINEERING_EXECUTOR_TIMEOUT"
    assert result["selected_provider"] == "agy"
    assert result["executor_provider"] == "agy"
    assert result["executor_timed_out"] is True
