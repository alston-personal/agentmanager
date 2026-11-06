"""AgentOS Interactive Approval Card Broker.

Bridges OpenMausBot-style interactive OptionCard approval flows with AgentOS
governance and non-blocking approval box. Allows mobile and remote operators to
inspect, approve, and reject sensitive actions (protected branch merges, external
publications, destructive commands) asynchronously without blocking the executor.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from . import config

APPROVAL_BOX_PATH = config.RUNTIME_DIR / "pending_approvals.json"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_box() -> dict[str, Any]:
    if not APPROVAL_BOX_PATH.exists():
        return {
            "schema": "agentos.approval-box/v1",
            "updated_at": _utc_now(),
            "pending_approvals": [],
            "history": [],
        }
    try:
        return json.loads(APPROVAL_BOX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema": "agentos.approval-box/v1",
            "updated_at": _utc_now(),
            "pending_approvals": [],
            "history": [],
        }


def save_box(data: dict[str, Any]) -> None:
    data["updated_at"] = _utc_now()
    APPROVAL_BOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVAL_BOX_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_approvals() -> dict[str, Any]:
    """Return all pending approvals and recent history formatted with OptionCard metadata."""
    box = load_box()
    pending = box.get("pending_approvals", [])
    history = box.get("history", [])

    cards = []
    for item in pending:
        cards.append(format_option_card(item))

    return {
        "protocol": "agentos.approval-card/v1",
        "pending_count": len(pending),
        "cards": cards,
        "pending": pending,
        "history": history[:20],
    }


def format_option_card(item: dict[str, Any]) -> dict[str, Any]:
    """Format a pending approval into an interactive OptionCard compatible with OpenMausBot and Web/Mobile."""
    return {
        "id": item.get("id"),
        "kind": "approval",
        "title": item.get("title") or f"Approval Request: {item.get('id')}",
        "subtitle": f"Project: {item.get('project_id')} | Actor: {item.get('actor')}",
        "action_type": item.get("action_type"),
        "payload": item.get("payload", {}),
        "next_unblocked_task": item.get("next_unblocked_task"),
        "status": item.get("status", "AWAITING_HUMAN_APPROVAL"),
        "parked_at": item.get("parked_at"),
        "options": [
            {"id": "approve", "label": "Approve", "variant": "success"},
            {"id": "reject", "label": "Reject", "variant": "danger"},
        ],
    }


def park_approval(
    approval_id: str,
    project_id: str,
    actor: str,
    title: str,
    action_type: str,
    payload: dict[str, Any] | None = None,
    next_unblocked_task: str = "",
) -> dict[str, Any]:
    box = load_box()
    for item in box["pending_approvals"]:
        if item["id"] == approval_id:
            return item

    entry = {
        "id": approval_id,
        "project_id": project_id,
        "actor": actor,
        "title": title,
        "action_type": action_type,
        "payload": payload or {},
        "next_unblocked_task": next_unblocked_task,
        "status": "AWAITING_HUMAN_APPROVAL",
        "parked_at": _utc_now(),
    }
    box["pending_approvals"].append(entry)
    save_box(box)
    return entry


def resolve_approval(
    approval_id: str,
    decision: str,
    approver: str = "human-operator",
    reason: str = "",
) -> dict[str, Any]:
    box = load_box()
    found = None
    remaining = []
    for item in box["pending_approvals"]:
        if item["id"] == approval_id:
            found = item
        else:
            remaining.append(item)

    if not found:
        return {"success": False, "error": f"Approval ID '{approval_id}' not found in pending list."}

    decision_norm = decision.strip().lower()
    if decision_norm in ("approve", "allow", "yes"):
        status = "APPROVED"
    elif decision_norm in ("reject", "deny", "no"):
        status = "REJECTED"
    else:
        return {"success": False, "error": f"Invalid decision '{decision}'. Must be 'approve' or 'reject'."}

    found["status"] = status
    found["resolved_at"] = _utc_now()
    found["resolved_by"] = approver
    if reason:
        found["reason"] = reason

    box["pending_approvals"] = remaining
    box.setdefault("history", []).insert(0, found)
    save_box(box)

    return {
        "success": True,
        "approval_id": approval_id,
        "status": status,
        "resolved_at": found["resolved_at"],
        "resolved_by": approver,
        "item": found,
    }
