from pathlib import Path

from agent_core.executor_job_contract import canonical_executor_job_request, canonical_gemini_cli_install_request
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry
from agentos_node.gemini_cli_install_provider import (
    EXECUTOR_CLASS,
    JOB_TYPE,
    PROVIDER_ID,
    register_gemini_cli_install_provider,
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
    assert _classify_install_failure(1, "npm ERR! network ENOTFOUND") == "GEMINI_CLI_INSTALL_NETWORK"
    assert _classify_install_failure(1, "npm ERR! code E404") == "GEMINI_CLI_INSTALL_NPM_FAILED"
    assert _classify_install_failure(7, "opaque failure") == "GEMINI_CLI_INSTALL_COMMAND_FAILED"


def test_gemini_cli_health_contract_is_read_only():
    from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
    request = canonical_executor_job_request("gemini.cli.health")
    spec = validate_executor_job(request)
    assert spec.executor_class == "gemini-cli"
    assert spec.capability == "agentos.executor.health.gemini-cli"
    assert spec.authority == "bounded-read-only"
    assert spec.read_only is True


def test_gemini_cli_health_uses_plan_mode_and_classifies_auth(monkeypatch):
    import agentos_node.gemini_cli_health_provider as provider

    class FakePath:
        def is_file(self): return True
    monkeypatch.setattr(provider, "GEMINI_BIN", FakePath())
    monkeypatch.setattr(provider.os, "access", lambda *args: True)
    monkeypatch.setattr(provider.Path, "home", staticmethod(lambda: provider.EXPECTED_HOME))
    monkeypatch.setenv("USER", "ubuntu")

    captured = {}
    class Completed:
        returncode = 1
        stdout = ""
        stderr = "Please login to continue"
    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return Completed()
    monkeypatch.setattr(provider.subprocess, "run", fake_run)

    result = provider.run_gemini_cli_health(
        canonical_executor_job_request("gemini.cli.health")
    )
    argv = captured["argv"]
    assert "--approval-mode" in argv
    assert argv[argv.index("--approval-mode") + 1] == "plan"
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert "yolo" not in argv
    assert result["classification"] == "GEMINI_CLI_AUTH_REQUIRED"
    assert result["credential_exposed"] is False


def test_gemini_cli_health_classifies_ready_and_rate_limit():
    from agentos_node.gemini_cli_health_provider import _classify
    assert _classify(0, '{"response":"READY"}') == "GEMINI_CLI_HEALTH_READY"
    assert _classify(1, "resource exhausted: quota exceeded") == "GEMINI_CLI_RATE_LIMITED"
