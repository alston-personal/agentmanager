from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos_node.executor_provider_registry import (
    load_provider,
    load_provider_profiles,
    validate_provider_profile,
)
from agentos_node.executor_provider_adapters import (
    AntigravityProvider,
    ClaudeCodeProvider,
    GeminiCliProvider,
    INVOKE_SCHEMA,
)
from agentos_node.codex_provider_adapter import CodexProvider


def test_core_profiles_load_and_bound_adapters():
    profiles = {p["executor_id"]: p for p in load_provider_profiles()}
    assert {"claude-code", "antigravity", "gemini", "codex"} <= set(profiles)

    claude = load_provider(profiles["claude-code"])
    antigravity = load_provider(profiles["antigravity"])
    gemini = load_provider(profiles["gemini"])
    codex = load_provider(profiles["codex"])

    assert isinstance(claude, ClaudeCodeProvider)
    assert isinstance(antigravity, AntigravityProvider)
    assert isinstance(gemini, GeminiCliProvider)
    assert isinstance(codex, CodexProvider)
    assert sorted(claude.capabilities()) == ["agent.chat", "code.edit"]
    assert sorted(antigravity.capabilities()) == ["agent.chat", "code.edit"]
    assert sorted(gemini.capabilities()) == ["agent.chat", "code.edit"]
    assert sorted(codex.capabilities()) == ["agent.chat", "code.edit"]


def test_provider_profile_rejects_caller_execution_authority():
    profile = {
        "schema": "agentos.executor-provider-profile/v0.1",
        "executor_id": "x",
        "provider_id": "x",
        "executor_class": "x",
        "modes": ["cli"],
        "capabilities": ["agent.chat"],
        "discovery": {
            "provider_owned_allowlists_only": True,
            "credential_access": False,
        },
        "invocation": {
            "bounded_semantic_requests_only": True,
            "caller_supplied_executable": True,
            "caller_supplied_argv": False,
            "caller_supplied_env": False,
        },
        "receipt": {"required": True, "secrets_allowed": False},
        "smoke": {"required": True},
        "adoption": {
            "reinstall_by_default": False,
            "preserve_existing_identity": True,
        },
        "implementation": {"adapter_module": None},
    }
    with pytest.raises(ValueError, match="caller_supplied_executable"):
        validate_provider_profile(profile)


def test_claude_invoke_maps_semantic_request_to_fixed_relay(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    workspace = tmp_path / "agentmanager"
    workspace.mkdir()
    monkeypatch.setitem(adapters.WORKSPACES, "agentos-core", workspace)

    calls = {}

    class FakeClient:
        def __init__(self, root):
            calls["root"] = str(root)

        def submit(self, **kwargs):
            calls.update(kwargs)
            return {"capsule_id": "relay-12345678"}

        def receipt(self, capsule_id):
            return None

    monkeypatch.setattr(adapters, "AntigravityRelayClient", FakeClient)

    provider = ClaudeCodeProvider(root=tmp_path / "relay")
    result = provider.invoke({
        "schema": INVOKE_SCHEMA,
        "operation": "code.edit",
        "project_id": "agentos-core",
        "workspace_ref": "agentos-core",
        "instruction": "Make the bounded test-only change.",
    })

    assert result["ok"] is True
    assert result["invocation_id"] == "relay-12345678"
    assert calls["executor_hint"] == "provider:claude"
    assert calls["workspace"] == str(workspace)
    assert calls["canonical_ir"]["operation"] == "code.edit"


def test_provider_invoke_rejects_unbounded_scope(tmp_path: Path):
    provider = AntigravityProvider(root=tmp_path / "relay")
    with pytest.raises(ValueError, match="scope"):
        provider.invoke({
            "schema": INVOKE_SCHEMA,
            "operation": "code.edit",
            "project_id": "agentos-core",
            "workspace_ref": "/tmp/arbitrary",
            "instruction": "noop",
        })


def test_provider_receipt_is_sanitized(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    class FakeClient:
        def __init__(self, root):
            pass

        def receipt(self, capsule_id):
            return {
                "schema": "agentos.antigravity-receipt/v1",
                "capsule_id": capsule_id,
                "provider": "agy",
                "returncode": 0,
                "ok": True,
                "timed_out": False,
                "stdout": "secret-output",
                "stderr": "secret-error",
            }

    monkeypatch.setattr(adapters, "AntigravityRelayClient", FakeClient)
    provider = AntigravityProvider(root=tmp_path / "relay")
    receipt = provider.receipt("relay-12345678")

    assert receipt["ok"] is True
    assert receipt["provider"] == "agy"
    assert receipt["classification"] == "COMPLETED"
    assert "stdout" not in receipt
    assert "stderr" not in receipt


def test_provider_health_classifies_cli_contract_without_leaking_output(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    monkeypatch.setattr(adapters, "_provider_command", lambda *args, **kwargs: ["agy", "run"])
    class Result:
        returncode = 2
        stdout = ""
        stderr = "Usage: agy [OPTIONS] COMMAND\nError: unknown command run"
    monkeypatch.setattr(adapters.subprocess, "run", lambda *args, **kwargs: Result())

    result = adapters._health("agy", workspace=tmp_path)
    assert result["state"] == "UNHEALTHY"
    assert result["classification"] == "CLI_CONTRACT"
    assert "stderr" not in result
    assert "stdout" not in result


def test_provider_health_classifies_rate_limit(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    monkeypatch.setattr(adapters, "_provider_command", lambda *args, **kwargs: ["agy"])
    class Result:
        returncode = 1
        stdout = ""
        stderr = "resource exhausted: quota exceeded"
    monkeypatch.setattr(adapters.subprocess, "run", lambda *args, **kwargs: Result())

    result = adapters._health("agy", workspace=tmp_path)
    assert result["classification"] == "RATE_LIMITED"


def test_claude_timeout_uses_partial_output_for_auth_classification(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    monkeypatch.setattr(adapters, "_provider_command", lambda *args, **kwargs: ["claude"])
    def timeout(*args, **kwargs):
        raise adapters.subprocess.TimeoutExpired(
            cmd=["claude"],
            timeout=1,
            output=b"",
            stderr=b"Please login to continue",
        )
    monkeypatch.setattr(adapters.subprocess, "run", timeout)

    result = adapters._health("claude", workspace=tmp_path, timeout_seconds=1)
    assert result["classification"] == "AUTH_REQUIRED"
    assert result["state"] == "AUTH_REQUIRED"
    assert result["authorized"] is False
    assert result["routable"] is False
    assert "stdout" not in result
    assert "stderr" not in result


def test_claude_timeout_preserves_timeout_when_partial_output_is_opaque(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    monkeypatch.setattr(adapters, "_provider_command", lambda *args, **kwargs: ["claude"])
    def timeout(*args, **kwargs):
        raise adapters.subprocess.TimeoutExpired(
            cmd=["claude"],
            timeout=1,
            output=b"starting",
            stderr=b"",
        )
    monkeypatch.setattr(adapters.subprocess, "run", timeout)

    result = adapters._health("claude", workspace=tmp_path, timeout_seconds=1)
    assert result["classification"] == "TIMEOUT"
    assert result["state"] == "UNHEALTHY"
    assert result["routable"] is False


def test_gemini_health_classifies_retired_consumer_oauth_without_leaking_output(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setattr(adapters, "_provider_command", lambda *args, **kwargs: ["gemini"])

    class Result:
        returncode = 1
        stdout = ""
        stderr = "IneligibleTierError: unsupported_client; this client is no longer supported"

    monkeypatch.setattr(adapters.subprocess, "run", lambda *args, **kwargs: Result())
    result = adapters._health("gemini", workspace=workspace, timeout_seconds=1)
    assert result["state"] == "UNHEALTHY"
    assert result["classification"] == "OAUTH_CLIENT_UNSUPPORTED"
    assert result["authorized"] is False
    assert result["routable"] is False
    assert "stderr" not in result
    assert "stdout" not in result


def test_gemini_health_uses_plan_mode_and_fixed_headless_prompt(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setattr(adapters, "discover_executor", lambda provider: ("gemini", ["/home/ubuntu/.local/bin/gemini"]))
    captured = {}

    class Result:
        returncode = 0
        stdout = "READY"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["cwd"] = kwargs.get("cwd")
        env = dict(kwargs.get("env") or {})
        settings = Path(env["GEMINI_CLI_HOME"]) / ".gemini" / "settings.json"
        captured["settings"] = json.loads(settings.read_text(encoding="utf-8"))
        captured["env"] = env
        return Result()

    monkeypatch.setattr(adapters.subprocess, "run", fake_run)
    result = adapters._health("gemini", workspace=workspace, timeout_seconds=1)
    argv = captured["argv"]
    assert "--approval-mode" in argv
    assert argv[argv.index("--approval-mode") + 1] == "plan"
    assert "-p" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "text"
    assert result["state"] == "READY"
    assert captured["settings"]["security"]["auth"]["selectedType"] == "oauth-personal"
    assert captured["settings"]["hooksConfig"]["enabled"] is False
    assert captured["settings"]["skills"]["enabled"] is False
    assert captured["env"]["HOME"] == "/home/ubuntu"
    assert captured["env"]["GEMINI_CLI_HOME"]
    assert captured["cwd"] != str(workspace)


def test_codex_health_requires_real_bounded_model_probe(monkeypatch, tmp_path: Path):
    import agentos_node.codex_provider_adapter as codex

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setitem(codex.WORKSPACES, "agentos-core", workspace)
    monkeypatch.setattr(codex, "_discover_codex", lambda: "/usr/local/bin/codex")
    calls = []

    def fake_run(executable, argv, **kwargs):
        calls.append((executable, list(argv), kwargs))
        if argv[:2] == ["login", "status"]:
            return 0, "Logged in", False
        return 0, "READY", False

    monkeypatch.setattr(codex, "_run", fake_run)
    result = codex.CodexProvider().health()
    assert result["state"] == "READY"
    assert result["classification"] == "READY"
    assert calls[0][1] == ["login", "status"]
    health_argv = calls[1][1]
    assert "exec" in health_argv
    assert "--sandbox" in health_argv
    assert health_argv[health_argv.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in health_argv


def test_codex_health_does_not_trust_login_status_when_inference_rejects_auth(monkeypatch, tmp_path: Path):
    import agentos_node.codex_provider_adapter as codex

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setitem(codex.WORKSPACES, "agentos-core", workspace)
    monkeypatch.setattr(codex, "_discover_codex", lambda: "/usr/local/bin/codex")

    responses = iter([
        (0, "Logged in", False),
        (1, "401 Unauthorized token_invalidated", False),
    ])
    monkeypatch.setattr(codex, "_run", lambda *args, **kwargs: next(responses))
    result = codex.CodexProvider().health()
    assert result["state"] == "AUTH_REQUIRED"
    assert result["classification"] == "AUTH_RUNTIME_REJECTED"
    assert result["authorized"] is False
    assert result["routable"] is False


def test_codex_health_reports_install_required_without_binary(monkeypatch):
    import agentos_node.codex_provider_adapter as codex

    monkeypatch.setattr(codex, "_discover_codex", lambda: None)
    result = codex.CodexProvider().health()
    assert result["state"] == "INSTALL_REQUIRED"
    assert result["classification"] == "INSTALL_REQUIRED"
    assert result["routable"] is False


def test_gemini_provider_health_uses_extended_bounded_timeout(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    captured = {}
    monkeypatch.setattr(adapters, "_health", lambda provider, **kwargs: captured.update(provider=provider, **kwargs) or {"state": "READY"})
    provider = adapters.GeminiCliProvider(tmp_path)
    result = provider.health()
    assert result["state"] == "READY"
    assert captured["provider"] == "gemini"
    assert captured["timeout_seconds"] == 60.0


def test_codex_health_requires_real_model_probe_after_login(monkeypatch, tmp_path: Path):
    import agentos_node.codex_provider_adapter as codex

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setitem(codex.WORKSPACES, "agentos-core", workspace)
    monkeypatch.setattr(codex, "_discover_codex", lambda: "/home/ubuntu/.local/bin/codex")
    calls = []

    def fake_run(executable, argv, **kwargs):
        calls.append(list(argv))
        if argv[:2] == ["login", "status"]:
            return 0, "Logged in using ChatGPT", False
        return 0, "READY", False

    monkeypatch.setattr(codex, "_run", fake_run)
    result = codex.CodexProvider().health()
    assert result["state"] == "READY"
    assert result["routable"] is True
    assert calls[0] == ["login", "status"]
    assert "exec" in calls[1]
    assert "read-only" in calls[1]


def test_codex_health_does_not_treat_runtime_401_as_ready(monkeypatch, tmp_path: Path):
    import agentos_node.codex_provider_adapter as codex

    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setitem(codex.WORKSPACES, "agentos-core", workspace)
    monkeypatch.setattr(codex, "_discover_codex", lambda: "/home/ubuntu/.local/bin/codex")

    responses = iter([
        (0, "Logged in using ChatGPT", False),
        (1, "401 Unauthorized: Incorrect API key provided", False),
    ])
    monkeypatch.setattr(codex, "_run", lambda *args, **kwargs: next(responses))
    result = codex.CodexProvider().health()
    assert result["classification"] == "AUTH_RUNTIME_REJECTED"
    assert result["authorized"] is False
    assert result["routable"] is False
    assert result["healthy"] is False
