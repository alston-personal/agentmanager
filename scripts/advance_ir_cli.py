#!/usr/bin/env python3
"""Standard CLI for inspecting and advancing AgentOS Canonical IR generations.

Replaces one-off manual scripts by providing a guarded, repeatable CLI that:
1. Inspects the current Canonical IR + active-continuation selector parity.
2. Advances the Canonical IR generation with CAS parent verification.
3. Atomically activates the new generation in active-continuation.json.
4. Optionally appends a sanitized summary of the durable Work Completion Ledger.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_core.active_continuation import (  # noqa: E402
    activate_continuation,
    read_active_continuation,
)
from agent_core.canonical_ir_handoff import advance_canonical_ir  # noqa: E402
from agent_core.resolve_facade import resolve_continuation  # noqa: E402


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _default_data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _completion_ledger_evidence(data_root: Path) -> dict[str, Any] | None:
    ledger_path = data_root / "governance" / "work-items.json"
    if not ledger_path.is_file():
        return None
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = payload.get("items")
    if not isinstance(items, dict):
        return None
    counts: dict[str, int] = {}
    for item in items.values():
        if isinstance(item, dict):
            st = str(item.get("status") or "unknown")
            counts[st] = counts.get(st, 0) + 1
    summary_parts = [f"{k}={v}" for k, v in sorted(counts.items())]
    return {
        "date": _utc_date(),
        "kind": "completion-ledger-snapshot",
        "verdict": "PASS",
        "summary": f"Completion ledger counts ({len(items)} total): " + ", ".join(summary_parts),
    }


def inspect_ir(
    project_id: str = "agentos-core",
    *,
    data_root: Path | None = None,
    governance_path: Path | None = None,
) -> dict[str, Any]:
    root = data_root or _default_data_root()
    resolved = resolve_continuation(project_id, data_root=root, governance_path=governance_path)
    head = resolved.get("execution_head") if isinstance(resolved.get("execution_head"), dict) else {}
    cont = resolved.get("continuation") if isinstance(resolved.get("continuation"), dict) else {}
    ir = cont.get("canonical_ir") if isinstance(cont.get("canonical_ir"), dict) else {}

    selector: dict[str, Any] | None = None
    selector_matches = False
    try:
        selector = read_active_continuation(root)
        selector_matches = (
            selector.get("project_id") == project_id
            and selector.get("index_id") == head.get("index_id")
            and selector.get("ir_id") == ir.get("ir_id")
        )
    except Exception:
        selector = None

    return {
        "ok": True,
        "project_id": project_id,
        "index_id": head.get("index_id"),
        "ir_id": ir.get("ir_id"),
        "parent_ir_id": ir.get("parent_ir_id"),
        "published_at": cont.get("published_at"),
        "updated_at": head.get("updated_at"),
        "goal": ir.get("goal"),
        "next_action": (ir.get("continuation") or {}).get("next_action") or cont.get("recommended_action"),
        "pending_tasks": ir.get("pending_tasks") or [],
        "decisions_count": len(ir.get("decisions") or []),
        "evidence_count": len(ir.get("evidence") or []),
        "active_selector": selector,
        "active_selector_matches": selector_matches,
    }


def advance_ir(
    *,
    project_id: str = "agentos-core",
    new_index_id: str,
    new_ir_id: str,
    goal: str,
    next_action: str,
    expected_index_id: str | None = None,
    expected_ir_id: str | None = None,
    pending_tasks: list[str] | None = None,
    decisions_append: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    include_completion_summary: bool = False,
    activate: bool = True,
    activation_reason: str | None = None,
    data_root: Path | None = None,
    governance_path: Path | None = None,
) -> dict[str, Any]:
    root = data_root or _default_data_root()
    current = inspect_ir(project_id, data_root=root, governance_path=governance_path)
    exp_index = expected_index_id or str(current.get("index_id") or "")
    exp_ir = expected_ir_id or str(current.get("ir_id") or "")

    ev_list = list(evidence or [])
    if include_completion_summary:
        snap = _completion_ledger_evidence(root)
        if snap is not None:
            ev_list.append(snap)

    handoff = advance_canonical_ir(
        {
            "project_id": project_id,
            "expected_index_id": exp_index,
            "expected_ir_id": exp_ir,
            "new_index_id": new_index_id,
            "new_ir_id": new_ir_id,
            "goal": goal,
            "next_action": next_action,
            "pending_tasks": pending_tasks if pending_tasks is not None else current.get("pending_tasks", []),
            "decisions_append": decisions_append or [],
            "evidence": ev_list,
        },
        data_root=root,
        governance_path=governance_path,
    )

    activation = None
    if activate:
        activation = activate_continuation(
            project_id,
            index_id=new_index_id,
            ir_id=new_ir_id,
            reason=activation_reason or f"advance active selector to {new_index_id}",
            data_root=root,
        )

    return {
        "ok": True,
        "handoff": handoff,
        "activation": activation,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or advance AgentOS Canonical IR")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--governance-path", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Inspect current Canonical IR and active selector parity")
    p_status.add_argument("--project-id", default="agentos-core")

    p_adv = sub.add_parser("advance", help="Advance Canonical IR generation and optionally activate selector")
    p_adv.add_argument("--project-id", default="agentos-core")
    p_adv.add_argument("--expected-index-id", default=None)
    p_adv.add_argument("--expected-ir-id", default=None)
    p_adv.add_argument("--new-index-id", required=True)
    p_adv.add_argument("--new-ir-id", required=True)
    p_adv.add_argument("--goal", required=True)
    p_adv.add_argument("--next-action", required=True)
    p_adv.add_argument("--pending-task", action="append", default=None)
    p_adv.add_argument("--decision", action="append", default=None)
    p_adv.add_argument("--include-completion-summary", action="store_true")
    p_adv.add_argument("--no-activate", action="store_true")
    p_adv.add_argument("--reason", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "status":
        out = inspect_ir(args.project_id, data_root=args.data_root, governance_path=args.governance_path)
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    out = advance_ir(
        project_id=args.project_id,
        expected_index_id=args.expected_index_id,
        expected_ir_id=args.expected_ir_id,
        new_index_id=args.new_index_id,
        new_ir_id=args.new_ir_id,
        goal=args.goal,
        next_action=args.next_action,
        pending_tasks=args.pending_task,
        decisions_append=args.decision,
        include_completion_summary=args.include_completion_summary,
        activate=not args.no_activate,
        activation_reason=args.reason,
        data_root=args.data_root,
        governance_path=args.governance_path,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
