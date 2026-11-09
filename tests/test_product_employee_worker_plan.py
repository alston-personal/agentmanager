from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "governance" / "product-employee-worker-plan.json"
ZEUS_BOOTSTRAP = ROOT / "governance" / "zeus-writer-employee.json"
YOUTUBE_BOOTSTRAP = ROOT / "governance" / "youtube-ai-manager-employee.json"
ADAPTERS = ROOT / "governance" / "employee-worker-adapters-v2.json"


def test_product_employee_worker_plan_is_bounded_and_shared_host_only():
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    assert payload["schema"] == "agentos.product-employee-worker-plan/v1"
    assert payload["shared_host_required"] is True

    runners = {item["runner_kind"]: item for item in payload["runners"]}
    assert set(runners) == {"zeus_writer_v1", "youtube_ai_manager_scan_v1"}

    zeus = runners["zeus_writer_v1"]
    assert zeus["employee_id"] == "zeus-writer"
    assert zeus["assignment_id"] == "zeus-writer-continuation-v1"
    assert zeus["role_ids"] == ["product.zeus_writer"]
    assert zeus["skill_ids"] == ["writing.project.continue"]
    assert zeus["network"] is False
    assert zeus["credentials"] is False
    assert zeus["external_mutation"] is False

    youtube = runners["youtube_ai_manager_scan_v1"]
    assert youtube["employee_id"] == "youtube-ai-manager"
    assert youtube["assignment_id"] == "youtube-ai-manager-scan-v1"
    assert youtube["role_ids"] == ["product.youtube_ai_manager"]
    assert youtube["skill_ids"] == ["youtube.optimization.scan"]
    assert youtube["network"] is False
    assert youtube["credentials"] is False
    assert youtube["external_mutation"] is False

    forbidden_keys = {"executable", "module", "argv", "shell", "url", "endpoint", "token", "secret"}
    for runner in runners.values():
        assert not (set(runner) & forbidden_keys)

    assert "one_shared_worker_host_not_daemon_per_role" in payload["invariants"]
    assert "exact_governed_wake_required_before_claim" in payload["invariants"]
    assert "unknown_runner_or_result_schema_fails_closed" in payload["invariants"]


def test_product_assignment_ids_match_bootstrap_and_worker_registry_exactly():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    zeus_bootstrap = json.loads(ZEUS_BOOTSTRAP.read_text(encoding="utf-8"))
    youtube_bootstrap = json.loads(YOUTUBE_BOOTSTRAP.read_text(encoding="utf-8"))
    adapters = json.loads(ADAPTERS.read_text(encoding="utf-8"))

    planned = {item["employee_id"]: item for item in plan["runners"]}
    registered = {item["employee_id"]: item for item in adapters["adapters"]}
    bootstraps = {
        "zeus-writer": zeus_bootstrap,
        "youtube-ai-manager": youtube_bootstrap,
    }

    for employee_id, bootstrap in bootstraps.items():
        work_item = bootstrap["initial_work_item"]
        assert planned[employee_id]["assignment_id"] == work_item["assignment_id"]
        assert registered[employee_id]["assignment_id"] == work_item["assignment_id"]
        assert planned[employee_id]["role_ids"] == bootstrap["employee"]["role_ids"]
        assert registered[employee_id]["role_ids"] == bootstrap["employee"]["role_ids"]
        assert planned[employee_id]["skill_ids"] == bootstrap["employee"]["skill_ids"]
        assert registered[employee_id]["skill_ids"] == bootstrap["employee"]["skill_ids"]
