#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.active_continuation import activate_continuation
from agent_core.canonical_ir_handoff import advance_canonical_ir
from agent_core.resolve_facade import resolve_continuation

PROJECT_ID = "agentos-core"
EXPECTED_INDEX = "idx-core-152"
EXPECTED_IR = "ir-core-152"
NEW_INDEX = "idx-core-152-e3-1"
NEW_IR = "ir-core-152-e3-1"
GOAL = (
    "Prove E3 continuity: Gemini -> AgentOS ONE -> a completely fresh Antigravity "
    "Codex executor continues from the authoritative Canonical IR without copied vendor history."
)
NEXT_ACTION = (
    "Reload Antigravity only if required by runtime changes, then open a completely fresh built-in "
    "Antigravity Codex conversation and send only '繼續'; verify it reports source=ONE_PREINVOCATION_IR, "
    "selection_source=ONE_ACTIVE_CONTINUATION, project=agentos-core, "
    "index_id=idx-core-152-e3-1, ir_id=ir-core-152-e3-1, and continues the E3 goal regardless of IDE workspace."
)


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _activate_e3(root: Path) -> dict:
    return activate_continuation(
        PROJECT_ID,
        index_id=NEW_INDEX,
        ir_id=NEW_IR,
        reason="#152 E3 cross-executor continuity is the active canonical task",
        data_root=root,
    )


def main() -> int:
    root = _data_root()
    current = resolve_continuation(PROJECT_ID, data_root=root)
    head = current.get("execution_head") if isinstance(current.get("execution_head"), dict) else {}
    continuation = current.get("continuation") if isinstance(current.get("continuation"), dict) else {}
    ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
    current_index = str(head.get("index_id") or "").strip()
    current_ir = str(ir.get("ir_id") or "").strip()

    if current_index == NEW_INDEX and current_ir == NEW_IR:
        activation = _activate_e3(root)
        print(
            json.dumps(
                {
                    "schema": "agentos.issue-152-e2-to-e3/v1",
                    "ok": True,
                    "advanced": False,
                    "reason": "already advanced; active selector reconciled",
                    "project_id": PROJECT_ID,
                    "index_id": NEW_INDEX,
                    "ir_id": NEW_IR,
                    "active_selector": activation,
                    "credential_exposed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if current_index != EXPECTED_INDEX or current_ir != EXPECTED_IR:
        print(
            json.dumps(
                {
                    "schema": "agentos.issue-152-e2-to-e3/v1",
                    "ok": False,
                    "advanced": False,
                    "reason": "unexpected canonical parent; refusing to overwrite",
                    "expected": {"index_id": EXPECTED_INDEX, "ir_id": EXPECTED_IR},
                    "found": {"index_id": current_index or None, "ir_id": current_ir or None},
                    "credential_exposed": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 3

    receipt = advance_canonical_ir(
        {
            "project_id": PROJECT_ID,
            "expected_index_id": EXPECTED_INDEX,
            "expected_ir_id": EXPECTED_IR,
            "new_index_id": NEW_INDEX,
            "new_ir_id": NEW_IR,
            "goal": GOAL,
            "next_action": NEXT_ACTION,
            "pending_tasks": [
                "Open a completely fresh built-in Antigravity Codex conversation and send only '繼續'.",
                "Verify the fresh Codex session receives ONE_PREINVOCATION_IR selected by ONE_ACTIVE_CONTINUATION with the E3 child generation regardless of current workspace.",
                "Capture a second fresh Codex regression before marking E3 stable for this surface.",
                "Persist sanitized E3 evidence and update AgentOS current state after live verification.",
            ],
            "decisions_append": [
                "E2 Antigravity Gemini fresh-session Canonical IR continuity is VERIFIED from two independent fresh sessions.",
                "Advance E2 -> E3 through the Core-owned guarded Canonical IR writer; executors do not directly mutate canonical state.",
                "Fresh executor continuation selection is owned by the ONE active-continuation pointer, not IDE workspacePaths.",
            ],
            "evidence": [
                {
                    "kind": "antigravity-gemini-fresh-ir-regression",
                    "verdict": "VERIFIED",
                    "summary": "Two independent fresh built-in Gemini conversations, each given only 繼續, recovered ONE_PREINVOCATION_IR for agentos-core with idx-core-152 / ir-core-152.",
                    "date": "2026-09-01",
                    "evidence_path": ".agentos/evidence/issue-152-antigravity-gemini-e2-2026-09-01.md",
                },
                {
                    "kind": "credential-boundary",
                    "verdict": "PASS",
                    "summary": "Oracle-local ONE projection and Antigravity MCP/bootstrap reported credential_exposed=false.",
                    "date": "2026-09-01",
                },
            ],
            "execution_status": "in_progress",
            "execution_metadata": {
                "issue": "#152",
                "phase": "E3-antigravity-codex-continuity",
                "e2_verdict": "VERIFIED",
            },
        },
        data_root=root,
    )
    activation = _activate_e3(root)
    print(
        json.dumps(
            {
                "schema": "agentos.issue-152-e2-to-e3/v1",
                "ok": True,
                "advanced": True,
                "project_id": PROJECT_ID,
                "parent": {"index_id": EXPECTED_INDEX, "ir_id": EXPECTED_IR},
                "child": {"index_id": NEW_INDEX, "ir_id": NEW_IR},
                "active_selector": activation,
                "credential_exposed": False,
                "handoff_receipt": receipt,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
