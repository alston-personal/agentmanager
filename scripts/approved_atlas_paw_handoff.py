"""Exact Atlas #2243 Completion WorkItem -> existing Paw read-only Assignment.

This is deliberately an observation bridge, not an engineering execution grant.
Canonical Atlas authority remains my-agent-data#22 and the Completion Ledger.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.core_work_items import WorkItemStore
from agent_core.employee_runtime import EmployeeRuntime

WORK_ID = "gh-issue-2243-engineering"
ASSIGNMENT_ID = "paw-atlas-2243-inspect-v1"
SOURCE = "https://github.com/alston-personal/agentmanager/issues/2243"
PROJECT = "agentos-atlas"
EMPLOYEE = "the-paw"
RECEIPT_SCHEMA = "agentos.approved-atlas-paw-handoff-receipt/v1"
GOAL = (
    "Inspect existing Atlas canonical issue my-agent-data#22, merged PR #21, "
    "live Delta ingress and Oracle Supervisor readiness. Report exact missing "
    "CI, install, Delta receipt, Resume readback and S4 assignment evidence. "
    "Do not modify repositories, run shell, deploy, or approve engineering work."
)
CONSTRAINTS = [
    "read-only-inspection-only",
    "do-not-execute-issue-markdown",
    "no-repository-write-merge-or-deploy",
    "no-cross-realm-or-credential-access",
    "canonical-atlas-work=my-agent-data#22",
    "no-completion-without-independent-evidence",
]


def handoff(*, completion_state: Path, runtime_root: Path) -> dict:
    completion = json.loads(completion_state.read_text(encoding="utf-8"))
    if completion.get("schema") != "agentos.work-completion/v1":
        raise ValueError("completion_ledger_schema_mismatch")
    item = (completion.get("items") or {}).get(WORK_ID)
    if not isinstance(item, dict):
        return {
            "schema": RECEIPT_SCHEMA, "work_id": WORK_ID,
            "assignment_id": ASSIGNMENT_ID, "assignment_registered": False,
            "status": "source_work_item_missing", "execution_authorized": False,
            "execution_started": False, "credential_exposed": False,
        }
    exact = {
        "work_id": WORK_ID, "project_id": PROJECT, "source": SOURCE,
        "owner": "role://completion.controller", "intake_kind": "engineering",
        "execution_authorized": False,
    }
    if any(item.get(key) != value for key, value in exact.items()):
        raise PermissionError("approved_atlas_work_item_contract_mismatch")
    if item.get("status") not in ("accepted", "in_progress"):
        return {
            "schema": RECEIPT_SCHEMA, "work_id": WORK_ID,
            "assignment_id": ASSIGNMENT_ID, "assignment_registered": False,
            "status": "waiting_for_completion_controller",
            "completion_state": str(item.get("status") or "unknown"),
            "execution_authorized": False, "execution_started": False,
            "credential_exposed": False,
        }
    if not isinstance(item.get("acceptance"), list) or not item["acceptance"]:
        raise PermissionError("approved_atlas_acceptance_missing")

    runtime = EmployeeRuntime(runtime_root)
    employee = runtime.get_employee(EMPLOYEE)
    if "sector.paw" not in employee.role_ids or "engineering.work.inspect" not in employee.skill_ids:
        raise PermissionError("paw_readonly_role_unavailable")
    store = WorkItemStore(runtime)
    work = store.persist({
        "schema": "agentos.core-work-item/v1",
        "work_item_id": ASSIGNMENT_ID,
        "source_kind": "canonical_state",
        "source_ref": "completion:" + WORK_ID,
        "project_id": PROJECT,
        "employee_id": EMPLOYEE,
        "assignment_id": ASSIGNMENT_ID,
        "goal": GOAL,
        "constraints": CONSTRAINTS,
        "dependency_refs": [],
        "required_capabilities": ["engineering.work.inspect"],
        "authority_requirements": ["one-governed-dispatch", "read-only-inspection-only"],
        "source_revision": "atlas-2243-readonly-inspection-v1",
        "state": "open",
    })
    assignment = store.project_pending_assignment(work.work_item_id)
    if assignment.state not in ("pending", "active", "blocked", "handoff", "completed"):
        raise RuntimeError("paw_assignment_state_invalid")
    return {
        "schema": RECEIPT_SCHEMA, "work_id": WORK_ID,
        "assignment_id": ASSIGNMENT_ID,
        "employee_id": EMPLOYEE, "assignment_state": assignment.state,
        "assignment_registered": True, "execution_authorized": False,
        "execution_started": False, "lease_id": None,
        "credential_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completion-state", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.completion_state.is_absolute() or not args.runtime_root.is_absolute():
        raise SystemExit("absolute_paths_required")
    print(json.dumps(
        handoff(completion_state=args.completion_state, runtime_root=args.runtime_root),
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
