from pathlib import Path

from agent_core.executor_job_contract import canonical_typesafe_skill_install_request
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry
from agentos_node.typesafe_skill_install_provider import (
    EXECUTOR_CLASS,
    JOB_TYPE,
    PROVIDER_ID,
    register_typesafe_skill_install_provider,
)


def test_typesafe_provider_registers_only_when_fixed_installer_exists(tmp_path: Path):
    registry = ExecutorJobProviderRegistry()
    assert register_typesafe_skill_install_provider(registry=registry, runtime_root=tmp_path) is False
    installer = tmp_path / "scripts/install_oracle_typesafe_skill.sh"
    installer.parent.mkdir(parents=True)
    installer.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    assert register_typesafe_skill_install_provider(registry=registry, runtime_root=tmp_path) is True
    binding = registry.get(JOB_TYPE)
    assert binding is not None
    assert binding.provider_id == PROVIDER_ID
    assert binding.executor_class == EXECUTOR_CLASS


def test_typesafe_request_has_no_caller_supplied_execution_fields():
    request = canonical_typesafe_skill_install_request()
    assert set(request) == {
        "schema", "job_type", "project_id", "executor_class", "workload_ref", "authority"
    }
    assert "command" not in request
    assert "argv" not in request
    assert "path" not in request
    assert "env" not in request


def test_typesafe_installer_uses_single_npx_method_and_copy_mode():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts/install_oracle_typesafe_skill.sh").read_text(encoding="utf-8")
    command = "npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --yes --copy"
    assert text.count("npx --yes skills add") == 1
    assert command in text
    assert "--global" not in text
    assert 'project_root="/home/ubuntu/agentmanager"' in text
    assert 'skill_file="$project_root/.agents/skills/typesafe-ai/SKILL.md"' in text
