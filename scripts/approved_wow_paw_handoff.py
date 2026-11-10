"""Exact approved #2134 completion work -> existing Paw read-only Employee assignment.

This source-controlled bridge is deliberately NOT a general Issue executor or
permission grant. Supervisor/ONE must still authorize delivery; Paw inspect
cannot modify files, merge, deploy, or close the Completion WorkItem.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.core_work_items import WorkItemStore
from agent_core.employee_runtime import EmployeeRuntime

WORK_ID = "gh-issue-2134-engineering"
ASSIGNMENT_ID = "paw-wow-2134-inspect-v1"
SOURCE = "https://github.com/alston-personal/agentmanager/issues/2134"
PROJECT = "wow-agentos-interface"
EMPLOYEE = "the-paw"
GOAL = (
    "Read-only inspection of existing WoW AgentOS #2134 and Draft PR #2135. "
    "Report source status, installation/Bridge/ONE gaps and separately governed "
    "engineering capability requirements; no code or production mutations."
)
CONSTRAINTS = [
    "read-only-inspection-only",
    "do-not-execute-issue-markdown",
    "no-repository-write-merge-or-deploy",
    "no-cross-realm-or-credential-access",
    "preserve-existing-pr-2135",
    "no-completion-without-independent-evidence",
]


def handoff(*, completion_state: Path, runtime_root: Path) -> dict:
    completion = json.loads(completion_state.read_text(encoding="utf-8"))
    if completion.get("schema") != "agentos.work-completion/v1":
        raise ValueError("completion_ledger_schema_mismatch")
    item = (completion.get("items") or {}).get(WORK_ID)
    if not isinstance(item, dict):
        raise ValueError("approved_wow_work_item_missing")
    exact = {
        "work_id": WORK_ID, "project_id": PROJECT, "source": SOURCE,
        "owner": "role://completion.controller", "intake_kind": "engineering",
        "execution_authorized": False,
    }
    if any(item.get(key) != value for key, value in exact.items()):
        raise PermissionError("approved_wow_work_item_contract_mismatch")
    # Inspection of a verification failure is independent of retrying the
    # original Completion WorkItem. A time wait or blocked state must never
    # be reset merely to allow a separately scoped read-only Paw inspection.
    # The original wait, retry budget and owner remain fully authoritative.
    verification_diagnostic = (
        item.get("status") in ("waiting_external", "blocked")
        and item.get("last_blocker_kind") == "VERIFICATION"
    )
    if item.get("status") in ("waiting_external", "blocked") and not verification_diagnostic:
        wake = item.get("wake_condition") or {}
        return {
            "schema": "agentos.approved-wow-paw-handoff-receipt/v1",
            "work_id": WORK_ID, "assignment_id": ASSIGNMENT_ID,
            "employee_id": EMPLOYEE, "assignment_state": "not_created",
            "assignment_registered": False,
            "status": "waiting_for_completion_controller",
            "completion_state": item["status"],
            "wake_kind": wake.get("kind") if wake.get("kind") in ("time", "external") else "none",
            "execution_authorized": False,
            "execution_started": False,
            "lease_id": None, "credential_exposed": False,
        }
    if item.get("status") not in ("accepted", "in_progress") and not verification_diagnostic:
        raise PermissionError("approved_wow_work_item_not_open")
    if not isinstance(item.get("acceptance"), list) or not item["acceptance"]:
        raise PermissionError("approved_wow_acceptance_missing")
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
        "source_revision": "wow-2134-readonly-inspection-v1",
        "state": "open",
    })
    assignment = store.project_pending_assignment(work.work_item_id)
    if assignment.state not in ("pending", "active", "blocked", "handoff", "completed"):
        raise RuntimeError("paw_assignment_state_invalid")
    # Do not tamper with active leases, inherited Paw thread heads or receipts.
    return {
        "schema": "agentos.approved-wow-paw-handoff-receipt/v1",
        "work_id": WORK_ID, "assignment_id": ASSIGNMENT_ID,
        "employee_id": EMPLOYEE, "assignment_state": assignment.state,
        "assignment_registered": True,
        "verification_remediation_only": verification_diagnostic,
        "execution_authorized": False,
        "execution_started": False,
        "lease_id": None,
        "credential_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completion-state", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.completion_state.is_absolute() or not args.runtime_root.is_absolute():
        raise SystemExit("absolute_paths_required")
    print(json.dumps(handoff(completion_state=args.completion_state,
                             runtime_root=args.runtime_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
