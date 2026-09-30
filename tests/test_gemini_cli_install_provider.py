from pathlib import Path

from agent_core.executor_job_contract import canonical_gemini_cli_install_request
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
