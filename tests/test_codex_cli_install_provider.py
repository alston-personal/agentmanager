from __future__ import annotations

import json
from pathlib import Path

from agent_core.executor_job_contract import canonical_codex_cli_install_request
from agentos_node.codex_cli_install_provider import (
    EXECUTOR_CLASS,
    PROVIDER_ID,
    register_codex_cli_install_provider,
    run_codex_cli_install,
)
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry


def test_codex_install_rejects_wrong_oracle_identity(tmp_path: Path, monkeypatch):
    import agentos_node.codex_cli_install_provider as provider

    monkeypatch.setattr(provider, "EXPECTED_HOME", tmp_path / "ubuntu")
    monkeypatch.setattr(provider, "DATA_ROOT", tmp_path / "ubuntu" / "agent-data")
    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: tmp_path / "wrong"))
    result = run_codex_cli_install(canonical_codex_cli_install_request(), runtime_root=tmp_path)
    assert result["classification"] == "CODEX_CLI_ORACLE_UBUNTU_IDENTITY_MISMATCH"
    assert result["successful"] is False


def test_codex_install_accepts_sanitized_receipt(tmp_path: Path, monkeypatch):
    import agentos_node.codex_cli_install_provider as provider

    home = tmp_path / "ubuntu"
    data = home / "agent-data"
    runtime = data / "runtime" / "codex-cli"
    runtime.mkdir(parents=True)
    script = tmp_path / "scripts" / "install_oracle_codex_cli.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n", encoding="utf-8")

    monkeypatch.setattr(provider, "EXPECTED_HOME", home)
    monkeypatch.setattr(provider, "DATA_ROOT", data)
    monkeypatch.setattr(provider, "RECEIPT_FILE", runtime / "install-receipt.json")
    monkeypatch.setattr(provider.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("USER", "ubuntu")

    class Result:
        returncode = 0
        stdout = "CODEX_CLI_INSTALL=PASS"
        stderr = ""

    def fake_run(*args, **kwargs):
        provider.RECEIPT_FILE.write_text(json.dumps({
            "schema": "agentos.codex-cli-install-receipt/v1",
            "codex_cli_version": "codex-cli 1.2.3",
            "cli_installed": True,
            "auth_ready": None,
            "credential_exposed": False,
        }), encoding="utf-8")
        return Result()

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    result = run_codex_cli_install(canonical_codex_cli_install_request(), runtime_root=tmp_path)
    assert result["classification"] == "CODEX_CLI_INSTALL_PASS"
    assert result["install_receipt_ok"] is True
    assert result["codex_cli_version"] == "codex-cli 1.2.3"
    assert result["authorized"] is False
    assert result["routable"] is False
    assert "stdout" not in result
    assert "stderr" not in result


def test_codex_install_provider_registers_only_fixed_job(tmp_path: Path):
    script = tmp_path / "scripts" / "install_oracle_codex_cli.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    registry = ExecutorJobProviderRegistry()
    assert register_codex_cli_install_provider(registry=registry, runtime_root=tmp_path) is True
    binding = registry.get("codex.cli.install")
    assert binding is not None
    assert binding.provider_id == PROVIDER_ID
    assert binding.executor_class == EXECUTOR_CLASS
