"""Read-only, fail-closed Employee roster for the authenticated operator surface.

This projection is not an execution carrier and never treats an Employee record,
a live lease, a Node heartbeat, or a historical receipt as proof of autonomous
product liveness. Scheduled/due and provider availability require separate
canonical sources and intentionally remain unknown here.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agent_core.employee_lifecycle import EmployeeLifecycle, RECEIPT_SCHEMA
from agent_core.employee_runtime import EmployeeRuntime

SCHEMA = "agentos.employee-roster/v1"
DEFAULT_EXPECTED = ("agentos-spec-steward", "zeus-writer", "youtube-ai-manager")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc)


def _last_terminal_receipt(lifecycle: EmployeeLifecycle, assignment_id: str, employee_id: str) -> dict[str, Any] | None:
    """Read only the fixed lifecycle receipt location, never a path from assignment.result."""
    directory = lifecycle.receipts_dir / assignment_id
    if not directory.is_dir():
        return None
    # Any corrupt receipt must not be silently skipped to invent a reliable last-success marker.
    valid: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != RECEIPT_SCHEMA
            or payload.get("employee_id") != employee_id
            or payload.get("assignment_id") != assignment_id
            or payload.get("outcome") not in {"completed", "blocked", "handoff", "cancelled"}
            or not isinstance(payload.get("generation"), int)
            or payload["generation"] < 1
            or path.stem != f"{payload['generation']:06d}"
        ):
            raise ValueError("invalid_employee_receipt")
        _parse(str(payload.get("recorded_at") or ""))
        valid.append(payload)
    if not valid:
        return None
    receipt = max(valid, key=lambda x: x["generation"])
    return {
        "generation": receipt["generation"],
        "outcome": receipt["outcome"],
        "recorded_at": receipt["recorded_at"],
        # Logical reference only. No arbitrary result, stdout, paths, prompt, private memory, model/session IDs.
        "evidence_ref": f"employee-receipt:{assignment_id}:{receipt['generation']}",
    }


def _assignment_projection(runtime: EmployeeRuntime, lifecycle: EmployeeLifecycle, assignment_id: str, now: datetime) -> dict[str, Any]:
    assignment = runtime.get_assignment(assignment_id)
    base: dict[str, Any] = {
        "assignment_id": assignment.assignment_id,
        "employee_id": assignment.employee_id,
        "state": "unknown",
        "blocker_code": None,
        "last_checkpoint_at": None,
        "last_terminal_receipt": None,
        "next_due_at": None,
        "schedule_verified": False,
        "executor_available": None,
        "product_work_verified": False,
    }
    try:
        receipt = _last_terminal_receipt(lifecycle, assignment.assignment_id, assignment.employee_id)
        base["last_terminal_receipt"] = receipt
        lease = lifecycle.get_lease(assignment.assignment_id)
        if assignment.state in {"completed", "cancelled", "blocked", "handoff"}:
            if not receipt or receipt["outcome"] != assignment.state:
                base["blocker_code"] = "terminal_receipt_missing_or_mismatch"
                return base
            base["state"] = assignment.state
        elif assignment.state == "pending":
            base["state"] = "pending"
        elif assignment.state == "active":
            if lease is None:
                base["blocker_code"] = "active_lease_missing"
            elif lease.status != "active":
                base["blocker_code"] = "active_lease_state_mismatch"
            elif lifecycle.lease_expired(lease, now=now):
                base["blocker_code"] = "expired_lease_prior_execution_unknown"
            else:
                base["state"] = "running"
                # Running means only a valid current lifecycle lease, NOT worker/product success.
            if lease is not None:
                base["last_checkpoint_at"] = lease.last_checkpoint_at
        else:
            base["blocker_code"] = "assignment_state_unrecognized"
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        base["state"] = "unknown"
        base["blocker_code"] = "canonical_lifecycle_evidence_invalid"
        base["last_terminal_receipt"] = None
    return base


def inspect_employee_roster(
    runtime_root: str | Path,
    *,
    expected_employee_ids: Iterable[str] = DEFAULT_EXPECTED,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Observe durable Employee identity and lifecycle only; no writes, wake or service activation."""
    root = Path(runtime_root)
    current = now or _utcnow()
    if current.tzinfo is None:
        raise ValueError("timezone_required")
    if not root.is_absolute():
        raise ValueError("runtime_root_must_be_absolute")
    runtime = EmployeeRuntime(root)
    lifecycle = EmployeeLifecycle(runtime)
    expected = set(expected_employee_ids)
    known = {p.stem for p in runtime.employees_dir.glob("*.json")} if runtime.employees_dir.is_dir() else set()
    roster: list[dict[str, Any]] = []
    for employee_id in sorted(known | expected):
        if not employee_id or any(ch in employee_id for ch in "/\\\0") or employee_id in {".", ".."}:
            continue
        item: dict[str, Any] = {
            "employee_id": employee_id,
            "registration": "unknown",
            "state": "unknown",
            "role_ids": [],
            "assignments": [],
            "blocker_code": None,
            "autonomous_liveness_verified": False,
        }
        if employee_id not in known:
            item["registration"] = "not_registered"
            item["blocker_code"] = "employee_identity_absent"
            roster.append(item)
            continue
        try:
            employee = runtime.get_employee(employee_id)
            item["registration"] = "registered"
            item["role_ids"] = sorted(employee.role_ids)
            assignments = []
            for path in sorted(runtime.assignments_dir.glob("*.json")) if runtime.assignments_dir.is_dir() else ():
                # An invalid assignment cannot be quietly dropped when auditing the roster.
                assignment = runtime.get_assignment(path.stem)
                if assignment.employee_id == employee_id:
                    assignments.append(_assignment_projection(runtime, lifecycle, assignment.assignment_id, current))
            item["assignments"] = assignments
            states = {a["state"] for a in assignments}
            if "unknown" in states:
                item["blocker_code"] = "assignment_evidence_incomplete"
            elif "running" in states:
                item["state"] = "running"
            elif "pending" in states:
                item["state"] = "pending"
            elif "blocked" in states:
                item["state"] = "blocked"
            elif assignments and states <= {"completed", "cancelled", "handoff"}:
                item["state"] = "idle"
            else:
                item["blocker_code"] = "no_current_assignment_or_schedule"
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            item["state"] = "unknown"
            item["blocker_code"] = "canonical_employee_record_invalid"
            item["assignments"] = []
            item["role_ids"] = []
        roster.append(item)
    return {
        "schema": SCHEMA,
        "observed_at": _iso(current),
        "source": "canonical_employee_runtime",
        "mode": "operator-local-readonly",
        "mutation_allowed": False,
        "supervisor_service_live": None,
        "one_route_live": None,
        "role_health_verified": False,
        "roles": roster,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only canonical Employee roster; not a liveness attestation")
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(inspect_employee_roster(args.runtime_root), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
