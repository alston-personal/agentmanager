from __future__ import annotations

import json
from pathlib import Path

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node import completion_next_inspect_provider as provider
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry, _sanitize_provider_result


def test_completion_next_inspect_contract_is_fixed_read_only():
    request = canonical_executor_job_request("completion.next.inspect")
    spec = validate_executor_job(request)
    assert spec.capability == "agentos.completion.work.inspect"
    assert spec.executor_class == "completion-controller"
    assert spec.project_id == "agentos-core"
    assert spec.workload_ref == "completion://next"
    assert spec.authority == "bounded-read-only"
    assert spec.read_only is True


def _fake_runtime(tmp_path: Path, payload) -> tuple[Path, Path]:
    state = tmp_path / "work-items.json"
    state.write_text('{"schema":"agentos.work-completion/v1","items":{}}\n', encoding="utf-8")
    script = tmp_path / "work_completion.py"
    script.write_text(
        "import json\nprint(" + repr(json.dumps(payload)) + ")\n",
        encoding="utf-8",
    )
    return state, script


def test_completion_next_inspect_returns_only_bounded_queue_head(tmp_path, monkeypatch):
    state, script = _fake_runtime(
        tmp_path,
        {
            "work_id": "agentos-core-470-runtime-completion",
            "project_id": "agentmanager",
            "status": "in_progress",
            "owner": "role://lobster",
            "owner_generation": 4,
            "next_action": "private detailed action",
            "acceptance": ["private acceptance"],
            "workspace": "/private/path",
        },
    )
    monkeypatch.setattr(provider, "STATE", state)
    monkeypatch.setattr(provider, "WORK_COMPLETION", script)

    result = provider.inspect_next_completion_work(
        canonical_executor_job_request("completion.next.inspect")
    )
    assert result["verdict"] == "PASS"
    assert result["classification"] == "COMPLETION_NEXT_WORK"
    assert result["work_id"] == "agentos-core-470-runtime-completion"
    assert result["completion_status"] == "in_progress"
    assert result["completion_owner"] == "role://lobster"
    assert result["completion_owner_generation"] == 4
    assert "next_action" not in result
    assert "workspace" not in result
    assert "acceptance" not in result


def test_completion_next_inspect_empty_queue_is_explicit(tmp_path, monkeypatch):
    state, script = _fake_runtime(tmp_path, None)
    monkeypatch.setattr(provider, "STATE", state)
    monkeypatch.setattr(provider, "WORK_COMPLETION", script)
    result = provider.inspect_next_completion_work(
        canonical_executor_job_request("completion.next.inspect")
    )
    assert result["classification"] == "COMPLETION_QUEUE_EMPTY"
    assert result["completion_status"] == "empty"
    assert result["successful"] is True


def test_completion_next_provider_registration_is_fixed():
    registry = ExecutorJobProviderRegistry()
    assert provider.register_completion_next_inspect_provider(registry) is True
    binding = registry.get("completion.next.inspect")
    assert binding is not None
    assert binding.provider_id == "completion-next-inspect-v1"
    assert binding.executor_class == "completion-controller"


def test_completion_next_result_sanitizer_drops_private_details():
    safe = _sanitize_provider_result(
        {
            "verdict": "PASS",
            "classification": "COMPLETION_NEXT_WORK",
            "work_id": "wi-safe",
            "completion_status": "accepted",
            "completion_owner": "role://completion.controller",
            "completion_owner_generation": 2,
            "next_action": "private",
            "workspace": "/private",
            "stdout": "private",
        }
    )
    assert safe["work_id"] == "wi-safe"
    assert safe["completion_status"] == "accepted"
    assert "next_action" not in safe
    assert "workspace" not in safe
    assert "stdout" not in safe
