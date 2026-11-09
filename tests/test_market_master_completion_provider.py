from __future__ import annotations

import json

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node import market_master_completion_provider as provider


def test_market_master_completion_job_contract_is_exact_and_bounded():
    request = canonical_executor_job_request("completion.market-master-1200.register")
    spec = validate_executor_job(request)
    assert spec.project_id == "market-master-evolution"
    assert spec.capability == "agentos.completion.work.register"
    assert spec.executor_class == "completion-controller"
    assert spec.workload_ref == "issue://1200"
    assert spec.authority == "bounded-work-intake"
    assert spec.read_only is False


def test_market_master_completion_provider_is_idempotent_for_existing_item(tmp_path, monkeypatch):
    state = tmp_path / "work-items.json"
    state.write_text(
        json.dumps(
            {
                "schema": "agentos.work-completion/v1",
                "generation": 1,
                "items": {
                    provider.WORK_ID: {
                        "work_id": provider.WORK_ID,
                        "status": "accepted",
                        "owner": "role://completion.controller",
                        "owner_generation": 3,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(provider, "STATE", state)

    result = provider.register_market_master_completion_work(
        canonical_executor_job_request("completion.market-master-1200.register")
    )

    assert result["verdict"] == "PASS"
    assert result["classification"] == "COMPLETION_WORK_ALREADY_REGISTERED"
    assert result["work_id"] == provider.WORK_ID
    assert result["completion_status"] == "accepted"
    assert result["completion_owner"] == "role://completion.controller"
    assert result["completion_owner_generation"] == 3
    assert result["successful"] is True


def test_market_master_completion_receipt_fields_are_bounded():
    from agentos_node.executor_job_adapter import _sanitize_provider_result

    safe = _sanitize_provider_result(
        {
            "verdict": "PASS",
            "classification": "COMPLETION_WORK_REGISTERED",
            "work_id": provider.WORK_ID,
            "completion_status": "accepted",
            "completion_owner": "role://completion.controller",
            "completion_owner_generation": 1,
            "stdout": "private",
            "path": "/home/ubuntu/private",
        }
    )
    assert safe["work_id"] == provider.WORK_ID
    assert safe["completion_status"] == "accepted"
    assert safe["completion_owner"] == "role://completion.controller"
    assert safe["completion_owner_generation"] == 1
    assert "stdout" not in safe
    assert "path" not in safe
