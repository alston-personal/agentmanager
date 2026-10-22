"""Fixed-scope, read-only #470 Ledger observability through existing ONE."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "completion.470.status.inspect"
PROVIDER_ID = "completion-470-status-inspect-v1"
STATE = Path("/home/ubuntu/agent-data/governance/work-items.json")
TARGET = "agentos-core-470-runtime-completion"
ACTIVE = {"accepted", "in_progress", "verifying", "blocked", "waiting_external"}
CORE_CURRENT = Path("/home/ubuntu/agent-data/runtime/core/current")
CORE_RELEASES = Path("/home/ubuntu/agent-data/releases/core")
PAW_BOOTSTRAP_RECEIPT = Path("/home/ubuntu/agent-data/employee-runtime/bootstrap/product-employees-v1.json")



def _paw_bootstrap_evidence() -> tuple[bool, bool, str]:
    """Inspect exact immutable release and bounded bootstrap receipt; no secrets."""
    if not CORE_CURRENT.is_symlink():
        return False, False, ""
    release = CORE_CURRENT.resolve(strict=True)
    release_root = CORE_RELEASES.resolve()
    if release.parent != release_root or len(release.name) != 40 or any(
        c not in "0123456789abcdef" for c in release.name
    ):
        return False, False, ""
    receipt = json.loads(PAW_BOOTSTRAP_RECEIPT.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        return True, False, release.name
    if receipt.get("schema") != "agentos.product-employee-bootstrap-receipt/v1" or receipt.get("ok") is not True:
        return True, False, release.name
    employees = receipt.get("employees")
    present = isinstance(employees, list) and any(
        isinstance(e, dict) and e.get("employee_id") == "the-paw"
        and e.get("assignment_id") == "paw-470-inspection-v1"
        and e.get("assignment_state") in {"pending", "accepted", "in_progress", "blocked", "completed", "handoff", "cancelled"}
        for e in employees
    )
    return True, present, release.name

def inspect_completion_470(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.workload_ref != "issue://470":
        return _fail("COMPLETION_470_CONTRACT_MISMATCH", authorized=False)
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
            raise ValueError("invalid_items")
        items = data["items"]
        if len(items) > 100000 or any(not isinstance(v, dict) for v in items.values()):
            raise ValueError("invalid_items")
        target = items.get(TARGET)
        if target is not None and not isinstance(target, dict):
            raise ValueError("invalid_target")
        counts = {key: 0 for key in ACTIVE}
        for item in items.values():
            status = item.get("status")
            if status in counts:
                counts[status] += 1
        status = str(target.get("status") or "missing") if target else "missing"
        if status not in ACTIVE | {"done", "cancelled", "failed", "missing"}:
            raise ValueError("invalid_status")
        verification = (target.get("verification") or {}) if target else {}
        if not isinstance(verification, dict):
            raise ValueError("invalid_verification")
        wake = (target.get("wake_condition") or {}) if target else {}
        if not isinstance(wake, dict):
            raise ValueError("invalid_wake")
        raw_due = str(wake.get("not_before") or "")
        wake_due = False
        if status == "waiting_external":
            if wake.get("kind") != "time" or not raw_due:
                raise ValueError("invalid_wake")
            due = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
            if due.tzinfo is None:
                raise ValueError("naive_wake")
            wake_due = due <= datetime.now(timezone.utc)
        history = target.get("history") or [] if target else []
        if not isinstance(history, list):
            raise ValueError("invalid_history")
        safe_events = {"wake", "wait_external", "machine_blocker_deferred", "stale_reclaim", "handoff", "transition", "heartbeat"}
        recent = [e for e in history[-100:] if isinstance(e, dict)]
        last_event = str(recent[-1].get("event") or "") if recent else ""
        last_event = last_event if last_event in safe_events else "other"
        kind = str(target.get("last_blocker_kind") or "") if target else ""
        if kind not in {"VERIFICATION", "PROVIDER_CAPACITY", "RUNTIME_HEALTH"}:
            kind = "UNKNOWN"
        retries = int(target.get("machine_retry_count") or 0) if target else 0
        if not 0 <= retries <= 1000000:
            raise ValueError("invalid_retry_count")
        try:
            release_valid, paw_bootstrapped, source_sha = _paw_bootstrap_evidence()
        except (OSError, ValueError, TypeError, KeyError):
            release_valid, paw_bootstrapped, source_sha = False, False, ""
        return {
            "runtime_source_commit": source_sha,
            "install_receipt_ok": release_valid,
            "hydration_receipt_ok": paw_bootstrapped,
            "completion_last_verification_failure_code": (
                str(target.get("last_verification_failure_code") or "")
                if target and str(target.get("last_verification_failure_code") or "") in {
                    "INSPECTOR_UNAVAILABLE", "PHYSICAL_OUTPUT", "TEST_FAILURE",
                    "EVIDENCE_MISSING", "ACCEPTANCE_FAILURE", "UNCLASSIFIED",
                } else "UNKNOWN"
            ),
            "completion_last_blocker_kind": kind,
            "completion_machine_retry_count": retries,
            "completion_last_event_category": last_event,
            "completion_recent_wake_count": sum(e.get("event") == "wake" for e in recent),
            "completion_recent_reclaim_count": sum(e.get("event") == "stale_reclaim" for e in recent),
            "completion_target_reclaimed": any(e.get("event") == "stale_reclaim" for e in recent),
            "completion_wake_not_before": raw_due if status == "waiting_external" else "",
            "completion_wake_overdue": wake_due,
            "completion_wait_reason_category": "present" if target and target.get("blocker") else "none",
            "verdict": "PASS",
            "classification": "COMPLETION_470_STATUS_OBSERVED",
            "executor_available": True, "routable": True,
            "authorized": True, "successful": True, "credential_exposed": False,
            "work_id": TARGET,
            "completion_status": status,
            "completion_owner": str(target.get("owner") or "")[:96] if target else "",
            "completion_owner_generation": int(target.get("owner_generation") or 0) if target else 0,
            "completion_active_count": sum(counts.values()),
            "completion_blocked_count": counts["blocked"],
            "completion_waiting_count": counts["waiting_external"],
            "completion_unreconciled_count": sum(
                1 for item in items.values()
                if item.get("status") in {"in_progress", "verifying"}
                and any(isinstance(e, dict) and e.get("event") == "stale_reclaim"
                        for e in (item.get("history") or []))
            ),
            "completion_target_verified": status == "done" and verification.get("status") == "passed",
        }
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return _fail("COMPLETION_470_STATUS_UNAVAILABLE")


def _fail(classification: str, *, authorized: bool = True) -> dict[str, Any]:
    return {
        "verdict": "FAIL", "classification": classification, "successful": False,
        "executor_available": True, "routable": authorized,
        "authorized": authorized, "credential_exposed": False,
    }


def register_completion_470_status_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    old = registry.get(JOB_TYPE)
    if old is not None:
        if old.provider_id == PROVIDER_ID and old.executor_class == "completion-controller":
            return True
        raise RuntimeError("Completion 470 status provider registered differently")
    registry.register(
        job_type=JOB_TYPE, provider_id=PROVIDER_ID,
        executor_class="completion-controller", handler=inspect_completion_470,
    )
    return True
