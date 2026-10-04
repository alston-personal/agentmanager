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
    GeminiProvider,
    INVOKE_SCHEMA,
)


def test_core_profiles_load_and_bound_adapters():
    profiles = {p["executor_id"]: p for p in load_provider_profiles()}
    assert {"claude-code", "antigravity", "gemini"} <= set(profiles)

    claude = load_provider(profiles["claude-code"])
    antigravity = load_provider(profiles["antigravity"])
    gemini = load_provider(profiles["gemini"])

    assert isinstance(claude, ClaudeCodeProvider)
    assert isinstance(antigravity, AntigravityProvider)
    assert isinstance(gemini, GeminiProvider)
    assert sorted(claude.capabilities()) == ["agent.chat", "code.edit"]
    assert sorted(antigravity.capabilities()) == ["agent.chat", "code.edit"]
    assert sorted(gemini.capabilities()) == ["agent.chat", "code.edit"]


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


def test_gemini_health_command_is_fixed_read_only_plan_mode(monkeypatch, tmp_path: Path):
    import agentos_node.executor_provider_adapters as adapters

    monkeypatch.setattr(adapters, "discover_executor", lambda provider: ("gemini", ["/home/ubuntu/.local/bin/gemini"]))
    argv = adapters._provider_command("gemini", tmp_path, "Reply exactly READY.")
    assert argv == [
        "/home/ubuntu/.local/bin/gemini",
        "-p", "Reply exactly READY.",
        "--approval-mode", "plan",
        "--skip-trust",
        "--output-format", "text",
    ]
