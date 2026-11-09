"""Hermes due-cycle projection through existing WorkItemStore.

Called only by the already-authorized, leader-owned Core Supervisor reconciliation.
No new timer, daemon, executor selection or grants. Only an explicitly authorized
Hermes predecessor with an independently persisted terminal Lifecycle Receipt may
generate one next-cycle WorkItem.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle

EMPLOYEE = "hermes-technology-scout"
SKILL = "github.technology.scan"
ROOT_ITEM = "hermes-2120-discovery-v1"
REQUIRED_AUTHORITY = "hermes-scheduled-continuation-authorized"
MIN_HOURS, MAX_HOURS = 1, 168


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("naive_receipt_timestamp")
    return result.astimezone(timezone.utc)


def project_due_hermes_cycle(
    store: WorkItemStore, lifecycle: EmployeeLifecycle, *, now: datetime,
) -> dict:
    """Idempotently materialize due next work; supervisor still owns dispatch."""
    if now.tzinfo is None:
        raise ValueError("timezone_aware_now_required")
    now = now.astimezone(timezone.utc)
    try:
        initial = store.get(ROOT_ITEM)
    except FileNotFoundError:
        return {"status":"not_configured"}
    if initial.employee_id != EMPLOYEE or SKILL not in initial.required_capabilities:
        return {"status":"invalid_configuration"}
    if REQUIRED_AUTHORITY not in initial.authority_requirements:
        return {"status":"not_authorized"}

    items = []
    for path in sorted(store.root.glob("*.json")):
        if path.stem != ROOT_ITEM and not path.stem.startswith(ROOT_ITEM+"-cycle-"):
            continue
        item = store.get(path.stem)
        if item.employee_id != EMPLOYEE or item.source_ref != initial.source_ref:
            return {"status":"conflicting_hermes_schedule"}
        items.append(item)
    if not items:
        return {"status":"missing_schedule"}
    # The newest cycle is determined by the deterministic cycle ordinal, not
    # filename ordering; gaps or malformed work must fail closed.
    def ordinal(item):
        if item.work_item_id == ROOT_ITEM:
            return 0
        suffix = item.work_item_id.removeprefix(ROOT_ITEM+"-cycle-")
        if not suffix.isdigit() or int(suffix) < 1:
            raise ValueError("invalid_hermes_cycle_id")
        return int(suffix)
    indexes = sorted((ordinal(item),item) for item in items)
    if [i for i,_ in indexes] != list(range(len(indexes))):
        return {"status":"cycle_sequence_gap"}
    i, previous = indexes[-1]
    try:
        assignment = lifecycle.runtime.get_assignment(previous.assignment_id)
    except FileNotFoundError:
        return {"status":"awaiting_assignment"}
    if assignment.state != "completed" or not isinstance(assignment.result,dict):
        return {"status":"awaiting_terminal_receipt"}
    generation = assignment.result.get("generation")
    if type(generation) is not int or generation < 1:
        return {"status":"invalid_terminal_receipt"}
    path = lifecycle._receipt_path(assignment.assignment_id,generation)
    lease = lifecycle.get_lease(assignment.assignment_id)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {"status":"missing_terminal_receipt"}
    if (not isinstance(receipt,dict) or not lease
        or assignment.result.get("receipt") != str(path.relative_to(lifecycle.runtime.root))
        or receipt.get("schema") != "agentos.employee-assignment-receipt/v1"
        or receipt.get("employee_id") != EMPLOYEE
        or receipt.get("assignment_id") != previous.assignment_id
        or receipt.get("lease_id") != lease.lease_id
        or receipt.get("generation") != generation
        or receipt.get("outcome") != "completed"
        or lease.status != "completed" or lease.generation != generation):
        return {"status":"invalid_terminal_receipt"}
    summary = receipt.get("result_summary")
    if (not isinstance(summary,dict)
        or summary.get("scan_schema") != "agentos.hermes-technology-scan/v1"
        or summary.get("scan_outcome") != "completed"):
        return {"status":"missing_scan_evidence"}
    hours = summary.get("next_interval_hours")
    if type(hours) is not int or not (MIN_HOURS <= hours <= MAX_HOURS):
        return {"status":"invalid_cadence"}
    due = _time(receipt["recorded_at"]) + timedelta(hours=hours)
    if now < due:
        return {"status":"not_due","next_eligible_at":due.isoformat()}
    next_id = f"{ROOT_ITEM}-cycle-{i+1:06d}"
    payload = {
        "schema":WORK_ITEM_SCHEMA,
        "work_item_id":next_id,
        "source_kind":"schedule",
        "source_ref":initial.source_ref,
        "project_id":initial.project_id,
        "employee_id":EMPLOYEE,
        "assignment_id":next_id,
        "goal":initial.goal,
        "constraints":list(initial.constraints),
        "dependency_refs":[],
        "required_capabilities":[SKILL],
        "authority_requirements":list(initial.authority_requirements),
        "source_revision":f"hermes-cycle-{i+1:06d}",
        "state":"open",
    }
    store.persist(payload)
    store.project_pending_assignment(next_id)
    return {"status":"projected","work_item_id":next_id,"next_eligible_at":due.isoformat()}
