#!/usr/bin/env python3
"""AgentOS Non-blocking Governance Approval Box.

Allows autonomous agents encountering Protected Branch or external publication
to asynchronously 'park' approval requests, notify the user, and switch to
the next unblocked task without stopping the entire system.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

APPROVAL_BOX_PATH = Path("/home/ubuntu/agent-data/runtime/pending_approvals.json")


def load_box() -> dict[str, Any]:
    if not APPROVAL_BOX_PATH.exists():
        return {
            "schema": "agentos.approval-box/v1",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pending_approvals": [],
            "history": []
        }
    try:
        return json.loads(APPROVAL_BOX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema": "agentos.approval-box/v1",
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pending_approvals": [],
            "history": []
        }


def save_box(data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    APPROVAL_BOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVAL_BOX_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def park_approval(
    approval_id: str,
    project_id: str,
    actor: str,
    title: str,
    action_type: str,
    payload: dict[str, Any],
    next_unblocked_task: str
) -> dict[str, Any]:
    box = load_box()
    # Check if already exists
    for item in box["pending_approvals"]:
        if item["id"] == approval_id:
            print(f"⚠️ Approval {approval_id} already pending.")
            return item

    entry = {
        "id": approval_id,
        "project_id": project_id,
        "actor": actor,
        "title": title,
        "action_type": action_type,
        "payload": payload,
        "next_unblocked_task": next_unblocked_task,
        "status": "AWAITING_HUMAN_APPROVAL",
        "parked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    box["pending_approvals"].append(entry)
    save_box(box)
    print(f"✅ Approval parked: [{approval_id}] {title}")
    print(f"🔄 Autonomous switch: proceeding with next unblocked task: '{next_unblocked_task}'")
    return entry


def resolve_approval(approval_id: str, decision: str, approver: str = "human-operator") -> bool:
    box = load_box()
    found = None
    remaining = []
    for item in box["pending_approvals"]:
        if item["id"] == approval_id:
            found = item
        else:
            remaining.append(item)

    if not found:
        print(f"❌ Approval ID {approval_id} not found in pending list.")
        return False

    found["status"] = "APPROVED" if decision.lower() == "approve" else "REJECTED"
    found["resolved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    found["resolved_by"] = approver

    box["pending_approvals"] = remaining
    box["history"].insert(0, found)
    save_box(box)
    print(f"✅ Resolved approval {approval_id} -> {found['status']} by {approver}")
    return True


def main():
    parser = argparse.ArgumentParser(description="AgentOS Governance Approval Box")
    sub = parser.add_subparsers(dest="cmd")

    list_p = sub.add_parser("list", help="List pending approvals")

    park_p = sub.add_parser("park", help="Park a task awaiting human approval")
    park_p.add_argument("--id", required=True)
    park_p.add_argument("--project", required=True)
    park_p.add_argument("--actor", default="agent")
    park_p.add_argument("--title", required=True)
    park_p.add_argument("--action-type", default="publish")
    park_p.add_argument("--next-task", default="none")

    resolve_p = sub.add_parser("resolve", help="Approve or reject a parked task")
    resolve_p.add_argument("--id", required=True)
    resolve_p.add_argument("--decision", choices=["approve", "reject"], required=True)
    resolve_p.add_argument("--approver", default="alston")

    args = parser.parse_args()

    if args.cmd == "list" or not args.cmd:
        box = load_box()
        pending = box.get("pending_approvals", [])
        print(f"📋 Pending Approvals ({len(pending)} total):")
        for p in pending:
            print(f" - [{p['id']}] ({p['project_id']}) {p['title']}")
            print(f"   Actor: {p['actor']} | Parked: {p['parked_at']}")
            print(f"   Switched To: {p['next_unblocked_task']}")
    elif args.cmd == "park":
        park_approval(args.id, args.project, args.actor, args.title, args.action_type, {}, args.next_task)
    elif args.cmd == "resolve":
        resolve_approval(args.id, args.decision, args.approver)


if __name__ == "__main__":
    main()

