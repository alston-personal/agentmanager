import json
from pathlib import Path

from agent_core.executor_job_contract import canonical_gemini_cli_health_request, canonical_gemini_cli_install_request
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry
from agentos_node.gemini_cli_install_provider import (
    EXECUTOR_CLASS,
    JOB_TYPE,
    PROVIDER_ID,
    HEALTH_JOB_TYPE,
    HEALTH_PROVIDER_ID,
    register_gemini_cli_install_provider,
    run_gemini_cli_health,
)


def test_gemini_cli_provider_registers_only_with_fixed_installer(tmp_path: Path):
    registry = ExecutorJobProviderRegistry()
    assert register_gemini_cli_install_provider(registry=registry, runtime_root=tmp_path) is False
    installer = tmp_path / "scripts/install_oracle_gemini_cli_one.sh"
    installer.parent.mkdir(parents=True)
    installer.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    assert register_gemini_cli_install_provider(registry=registry, runtime_root=tmp_path) is True
    binding = registry.get(JOB_TYPE)
    assert binding is not None
    assert binding.provider_id == PROVIDER_ID
    assert binding.executor_class == EXECUTOR_CLASS
    health = registry.get(HEALTH_JOB_TYPE)
    assert health is not None
    assert health.provider_id == HEALTH_PROVIDER_ID
    assert health.executor_class == EXECUTOR_CLASS


def test_gemini_cli_request_is_semantic_only():
    request = canonical_gemini_cli_install_request()
    assert request == {
        "schema": "agentos.executor-job/v1",
        "job_type": "gemini.cli.install",
        "project_id": "agentos-core",
        "executor_class": "gemini-cli",
        "workload_ref": "surface://gemini-cli",
        "authority": "oracle-user-gemini-cli-install",
    }
    for field in ("command", "argv", "path", "env", "token", "credential"):
        assert field not in request


def test_oracle_installer_uses_user_owned_npm_prefix_and_local_bin():
    text = Path("scripts/install_oracle_gemini_cli_one.sh").read_text(encoding="utf-8")
    assert 'npm_prefix="$HOME/.local/share/agentos/npm-global"' in text
    assert 'local_bin="$HOME/.local/bin"' in text
    assert 'npm install --prefix "$npm_prefix" -g @google/gemini-cli@latest' in text
    assert 'ln -sfn "$npm_prefix/bin/gemini" "$local_bin/gemini"' in text
    assert 'npm install -g @google/gemini-cli@latest' not in text


def test_gemini_cli_install_failure_classification_is_bounded():
    from agentos_node.gemini_cli_install_provider import _classify_install_failure

    assert _classify_install_failure(2, "ERROR: run as Oracle ubuntu user") == "GEMINI_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH"
    assert _classify_install_failure(3, "ERROR: missing prerequisite: npm") == "GEMINI_CLI_PREREQUISITE_MISSING"
    assert _classify_install_failure(4, "ERROR: AgentOS data root missing") == "GEMINI_CLI_AGENT_DATA_ROOT_UNAVAILABLE"
    assert _classify_install_failure(1, "npm ERR! code EACCES permission denied") == "GEMINI_CLI_INSTALL_PERMISSION_DENIED"
    assert _classify_install_failure(1, "npm ERR! code EBADENGINE Unsupported engine") == "GEMINI_CLI_NODE_INCOMPATIBLE"
    assert _classify_install_failure(1, "npm ERR! network ENOTFOUND") == "GEMINI_CLI_INSTALL_NETWORK"
    assert _classify_install_failure(1, "npm ERR! code E404") == "GEMINI_CLI_PACKAGE_UNAVAILABLE"
    assert _classify_install_failure(1, "npm ERR! code EUNKNOWN") == "GEMINI_CLI_INSTALL_NPM_FAILED"
    assert _classify_install_failure(7, "opaque failure") == "GEMINI_CLI_INSTALL_COMMAND_FAILED"


def test_gemini_cli_health_request_is_read_only_semantic_job():
    request = canonical_gemini_cli_health_request()
    assert request == {
        "schema": "agentos.executor-job/v1",
        "job_type": "gemini.cli.health",
        "project_id": "agentos-core",
        "executor_class": "gemini-cli",
        "workload_ref": "surface://gemini-cli",
        "authority": "bounded-read-only",
    }


def test_gemini_cli_health_classification_is_bounded():
    from agentos_node.gemini_cli_install_provider import _classify_health_failure

    assert _classify_health_failure(1, "Please login to continue") == "GEMINI_CLI_AUTH_REQUIRED"
    assert _classify_health_failure(1, "resource exhausted: quota") == "GEMINI_CLI_RATE_LIMITED"
    assert _classify_health_failure(1, "network is unreachable") == "GEMINI_CLI_NETWORK"
    assert _classify_health_failure(1, "Unknown argument: --approval-mode") == "GEMINI_CLI_CLI_CONTRACT"
    assert _classify_health_failure(1, "Workspace trust is required") == "GEMINI_CLI_WORKSPACE_TRUST_REQUIRED"
    assert _classify_health_failure(1, "settings.json invalid configuration") == "GEMINI_CLI_CONFIG_ERROR"
    assert _classify_health_failure(1, "SessionStart hook failed") == "GEMINI_CLI_HOOK_ERROR"
    assert _classify_health_failure(1, "agentos-one MCP unavailable") == "GEMINI_CLI_MCP_ERROR"
    assert _classify_health_failure(7, "opaque") == "GEMINI_CLI_HEALTH_NONZERO"
    assert _classify_health_failure(124, "", timed_out=True) == "GEMINI_CLI_HEALTH_TIMEOUT"


def test_gemini_cli_health_uses_fixed_headless_plan_mode(tmp_path, monkeypatch):
    import agentos_node.gemini_cli_install_provider as provider

    fake_home = tmp_path / "ubuntu"
    gemini = fake_home / ".local/bin/gemini"
    gemini.parent.mkdir(parents=True)
    gemini.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(provider, "EXPECTED_HOME", fake_home)
    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("USER", "ubuntu")

    captured = {}
    class Result:
        returncode = 0
        stdout = '{"response":"READY","stats":{},"error":null}'
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        settings = Path(kwargs["env"]["GEMINI_CLI_HOME"]) / ".gemini" / "settings.json"
        captured["settings"] = json.loads(settings.read_text(encoding="utf-8"))
        return Result()

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    result = run_gemini_cli_health(canonical_gemini_cli_health_request())
    assert result["classification"] == "GEMINI_CLI_HEALTH_READY"
    assert result["authorized"] is True
    assert result["routable"] is True
    argv = captured["argv"]
    assert "-p" in argv
    assert "--approval-mode" in argv
    assert argv[argv.index("--approval-mode") + 1] == "plan"
    assert "--skip-trust" in argv
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"


def test_gemini_cli_health_disables_workspace_hooks_without_changing_home(tmp_path, monkeypatch):
    import agentos_node.gemini_cli_install_provider as provider

    fake_home = tmp_path / "ubuntu"
    gemini = fake_home / ".local/bin/gemini"
    gemini.parent.mkdir(parents=True)
    gemini.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(provider, "EXPECTED_HOME", fake_home)
    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("USER", "ubuntu")

    seen = {}
    class Result:
        returncode = 0
        stdout = '{"response":"READY","stats":{},"error":null}'
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["cwd"] = kwargs["cwd"]
        seen["home"] = kwargs["env"]["HOME"]
        seen["cli_home"] = kwargs["env"]["GEMINI_CLI_HOME"]
        seen["settings"] = json.loads((Path(seen["cli_home"]) / ".gemini/settings.json").read_text(encoding="utf-8"))
        return Result()

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    result = run_gemini_cli_health(canonical_gemini_cli_health_request())
    assert result["classification"] == "GEMINI_CLI_HEALTH_READY"
    assert seen["home"] == str(fake_home)
    assert seen["cli_home"]
    assert seen["settings"]["security"]["auth"]["selectedType"] == "oauth-personal"
    assert seen["settings"]["hooksConfig"]["enabled"] is False
    assert seen["settings"]["skills"]["enabled"] is False
    assert seen["cwd"] != "/home/ubuntu/agentmanager"


def test_gemini_json_error_classification_is_bounded():
    from agentos_node.gemini_cli_install_provider import _classify_gemini_json_error

    assert _classify_gemini_json_error("FatalAuthenticationError", 1, 1) == "GEMINI_CLI_AUTH_REQUIRED"
    assert _classify_gemini_json_error("ResourceExhaustedError", 1, 1) == "GEMINI_CLI_RATE_LIMITED"
    assert _classify_gemini_json_error("FatalConfigError", 1, 1) == "GEMINI_CLI_CONFIG_ERROR"
    assert _classify_gemini_json_error("BadRequestError", 1, 1) == "GEMINI_CLI_API_REQUEST_ERROR"
    assert _classify_gemini_json_error("MysteryProviderError", 1, 1) == "GEMINI_CLI_API_ERROR"
    assert _classify_gemini_json_error("", None, 42) == "GEMINI_CLI_CLI_CONTRACT"
    assert _classify_gemini_json_error("", None, 53) == "GEMINI_CLI_TURN_LIMIT"
