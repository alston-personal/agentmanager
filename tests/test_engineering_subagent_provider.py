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
