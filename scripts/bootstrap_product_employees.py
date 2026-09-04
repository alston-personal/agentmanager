from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import EmployeeRuntime

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATHS = (
    ROOT / "governance" / "zeus-writer-employee.json",
    ROOT / "governance" / "youtube-ai-manager-employee.json",
)
TERMINAL_STATES = {"blocked", "handoff", "completed", "cancelled"}


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "agentos.employee-bootstrap/v1":
        raise ValueError(f"invalid_product_employee_bootstrap:{path.name}")
    return payload


def _exact_list(value: Any) -> list[str]:
    return [str(item) for item in (value or [])]


def bootstrap_contract(runtime: EmployeeRuntime, contract: dict[str, Any]) -> dict[str, Any]:
    employee_spec = dict(contract["employee"])
    work = dict(contract["initial_work_item"])
    employee_id = str(employee_spec["employee_id"])
    assignment_id = str(work["assignment_id"])
    initial_head = str(contract["initial_thread_head"])
    expected_roles = _exact_list(employee_spec.get("role_ids"))
    expected_skills = _exact_list(employee_spec.get("skill_ids"))
    expected_constraints = _exact_list(work.get("constraints"))

    employee_created = False
    try:
        employee = runtime.get_employee(employee_id)
    except FileNotFoundError:
        employee = runtime.create_employee(
            employee_id,
            str(employee_spec.get("display_name") or employee_id),
            role_ids=expected_roles,
            skill_ids=expected_skills,
        )
        employee_created = True
    else:
        if employee.display_name != str(employee_spec.get("display_name") or employee_id):
            raise RuntimeError(f"product_employee_display_name_mismatch:{employee_id}")
        if employee.role_ids != expected_roles:
            raise RuntimeError(f"product_employee_role_mismatch:{employee_id}")
        if employee.skill_ids != expected_skills:
            raise RuntimeError(f"product_employee_skill_mismatch:{employee_id}")

    assignment_created = False
    try:
        assignment = runtime.get_assignment(assignment_id)
    except FileNotFoundError:
        assignment = runtime.create_assignment(
            assignment_id,
            employee_id,
            str(work["goal"]),
            thread_head=initial_head,
            constraints=expected_constraints,
        )
        assignment_created = True
    else:
        if assignment.employee_id != employee_id:
            raise RuntimeError(f"product_assignment_employee_mismatch:{assignment_id}")
        if assignment.goal != str(work["goal"]):
            raise RuntimeError(f"product_assignment_goal_mismatch:{assignment_id}")
        if assignment.constraints != expected_constraints:
            raise RuntimeError(f"product_assignment_constraints_mismatch:{assignment_id}")
        # Existing state is authoritative. Never reopen a terminal assignment and
        # never replace a progressed durable thread head with the bootstrap head.
        if assignment.state in TERMINAL_STATES:
            return {
                "employee_id": employee_id,
                "assignment_id": assignment_id,
                "employee_created": employee_created,
                "assignment_created": False,
                "assignment_state": assignment.state,
                "thread_head": assignment.thread_head,
                "terminal_preserved": True,
                "progress_preserved": assignment.thread_head != initial_head,
            }

    return {
        "employee_id": employee_id,
        "assignment_id": assignment_id,
        "employee_created": employee_created,
        "assignment_created": assignment_created,
        "assignment_state": assignment.state,
        "thread_head": assignment.thread_head,
        "terminal_preserved": False,
        "progress_preserved": (not assignment_created and assignment.thread_head != initial_head),
    }


def bootstrap_all(runtime_root: Path) -> dict[str, Any]:
    runtime = EmployeeRuntime(runtime_root)
    results = [bootstrap_contract(runtime, _load_contract(path)) for path in CONTRACT_PATHS]
    receipt = {
        "schema": "agentos.product-employee-bootstrap-receipt/v1",
        "ok": True,
        "runtime_root": str(runtime.root),
        "employees": results,
        "executor_bound": False,
        "credential_exposed": False,
        "verified_marker_emitted": False,
    }
    receipt_path = runtime.root / "bootstrap" / "product-employees-v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bootstrap-product-employees")
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.runtime_root.expanduser()
    if not root.is_absolute():
        raise SystemExit("runtime root must be absolute")
    receipt = bootstrap_all(root.resolve())
    # Sanitized: no Employee memory, token, provider/model or session identity.
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
