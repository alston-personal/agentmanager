"""Idempotent, explicit Hermes Employee bootstrap into the existing Runtime.

This module does not run the Supervisor, grant capabilities, or claim liveness.
It is a deployment step, separate from recurring task delivery and ONE authority.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.core_work_items import WorkItemStore
from agent_core.role_runtime import RoleRegistry

EMPLOYEE_ID = "hermes-technology-scout"
ROLE_ID = "research.hermes"


def ensure_hermes_employee(runtime: EmployeeRuntime, registry: RoleRegistry,
                           bootstrap: dict) -> dict:
    employee = bootstrap["employee"]
    work = bootstrap["initial_work_item"]
    if employee.get("employee_id") != EMPLOYEE_ID or employee.get("role_ids") != [ROLE_ID]:
        raise ValueError("hermes_bootstrap_identity_mismatch")
    registry.resolve(ROLE_ID)
    if work.get("employee_id") != EMPLOYEE_ID:
        raise ValueError("hermes_assignment_identity_mismatch")
    action = "exists"
    try:
        current = runtime.get_employee(EMPLOYEE_ID)
        if ROLE_ID not in current.role_ids:
            raise RuntimeError("existing_employee_role_mismatch")
    except FileNotFoundError:
        runtime.create_employee(EMPLOYEE_ID, employee.get("display_name", "Hermes"),
                                role_ids=[ROLE_ID], skill_ids=employee.get("skill_ids", []))
        action = "created"

    # Canonical WorkItemStore is the sole source for Supervisor work projection.
    # The schedule/authority declaration must be installed by the trusted operator.
    store = WorkItemStore(runtime)
    stored = store.persist(work)
    assignment_id = stored.assignment_id
    try:
        current_assignment = runtime.get_assignment(assignment_id)
        if current_assignment.employee_id != EMPLOYEE_ID:
            raise RuntimeError("existing_assignment_owner_mismatch")
        assignment_action = "preserved"
    except FileNotFoundError:
        store.project_pending_assignment(stored.work_item_id)
        if bootstrap.get("initial_thread_head"):
            runtime.update_assignment(assignment_id, thread_head=str(bootstrap["initial_thread_head"]))
        assignment_action = "created"
    return {
        "schema": "agentos.hermes-bootstrap-result/v1",
        "employee_id": EMPLOYEE_ID,
        "employee_state": action,
        "assignment_id": assignment_id,
        "assignment_state": assignment_action,
        "runtime_wake_verified": False,
        "continuous_operation_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--role-registry", required=True)
    parser.add_argument("--bootstrap-json", required=True)
    args = parser.parse_args()
    bootstrap = json.loads(Path(args.bootstrap_json).read_text(encoding="utf-8"))
    result = ensure_hermes_employee(
        EmployeeRuntime(Path(args.runtime_root)), RoleRegistry(Path(args.role_registry)),
        bootstrap)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
