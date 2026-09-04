from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _roles() -> dict[str, dict]:
    data = yaml.safe_load((ROOT / ".agent/roles/registry.yaml").read_text(encoding="utf-8"))
    return {item["id"]: item for item in data["roles"]}


def _skills() -> dict[str, dict]:
    data = json.loads((ROOT / "governance/employee-skills.json").read_text(encoding="utf-8"))
    return data["skills"]


def _bootstrap(name: str) -> dict:
    return json.loads((ROOT / "governance" / name).read_text(encoding="utf-8"))


def _assert_contract(bootstrap_name: str, role_id: str, skill_id: str, capability: str) -> None:
    roles = _roles()
    skills = _skills()
    bootstrap = _bootstrap(bootstrap_name)

    assert role_id in roles
    assert roles[role_id]["status"] == "active"
    assert capability in roles[role_id]["capabilities"]

    assert skill_id in skills
    assert skills[skill_id]["status"] == "active"
    assert skills[skill_id]["mutation_authority"] is False
    assert skills[skill_id]["required_capabilities"] == [capability]

    employee = bootstrap["employee"]
    work_item = bootstrap["initial_work_item"]
    assert employee["role_ids"] == [role_id]
    assert employee["skill_ids"] == [skill_id]
    assert work_item["employee_id"] == employee["employee_id"]
    assert work_item["required_capabilities"] == [capability]
    assert "github_actions_is_not_control_plane_fallback" in bootstrap["invariants"] or "github-actions-is-not-control-plane-fallback" in bootstrap["invariants"]


def test_zeus_writer_product_employee_contract_is_bounded() -> None:
    _assert_contract(
        "zeus-writer-employee.json",
        "product.zeus_writer",
        "writing.project.continue",
        "writing.project.continue",
    )
    bootstrap = _bootstrap("zeus-writer-employee.json")
    constraints = bootstrap["initial_work_item"]["constraints"]
    assert "no-protected-branch-publication-authority" in constraints
    assert "no-foreign-product-carrier-development" in constraints
    assert "canonical-ir-and-employee-state-override-legacy-pulse-status-or-possession-directives" in constraints


def test_youtube_ai_manager_product_employee_contract_is_read_only_first() -> None:
    _assert_contract(
        "youtube-ai-manager-employee.json",
        "product.youtube_ai_manager",
        "youtube.optimization.scan",
        "youtube.optimization.scan",
    )
    bootstrap = _bootstrap("youtube-ai-manager-employee.json")
    constraints = bootstrap["initial_work_item"]["constraints"]
    assert "read-only-first" in constraints
    assert "no-external-youtube-api-mutation-authority" in constraints
    assert "status-or-memory-symlinks-are-not-liveness-proof" in constraints
