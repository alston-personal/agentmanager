#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.active_continuation import activate_continuation
from agent_core.canonical_ir_handoff import advance_canonical_ir
from agent_core.resolve_facade import resolve_continuation

PROJECT_ID = "agentos-core"
EXPECTED_INDEX = "idx-core-152-e3-codex-ext-1"
EXPECTED_IR = "ir-core-152-e3-codex-ext-1"
NEW_INDEX = "idx-core-152-post-e3-1"
NEW_IR = "ir-core-152-post-e3-1"
GOAL = (
    "Continue AgentOS Core #152 after verified Gemini -> ONE -> OpenAI Codex IDE extension E3 continuity; "
    "finish the broader durable Node-vs-executor extraction without regressing the verified continuity slice."
)
NEXT_ACTION = (
    "Resume #152 broader Node/executor extraction: make executor availability/freshness explicit and separate from Node liveness, "
    "reconcile executor lifecycle/bridge responsibilities with the existing session bridge without duplicate authority, "
    "then obtain the remaining real-client acceptance evidence. Do not repeat the completed Codex E3 fresh-thread regression."
)


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _activate(root: Path) -> dict:
    return activate_continuation(
        PROJECT_ID,
        index_id=NEW_INDEX,
        ir_id=NEW_IR,
        reason="#152 E3 cross-extension continuity verified; resume broader Node/executor extraction",
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
        activation = _activate(root)
        print(json.dumps({
            "schema": "agentos.issue-152-post-e3/v1",
            "ok": True,
            "advanced": False,
            "reason": "already advanced; active selector reconciled",
            "project_id": PROJECT_ID,
            "index_id": NEW_INDEX,
            "ir_id": NEW_IR,
            "active_selector": activation,
            "credential_exposed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if current_index != EXPECTED_INDEX or current_ir != EXPECTED_IR:
        print(json.dumps({
            "schema": "agentos.issue-152-post-e3/v1",
            "ok": False,
            "advanced": False,
            "reason": "unexpected canonical parent; refusing to overwrite",
            "expected": {"index_id": EXPECTED_INDEX, "ir_id": EXPECTED_IR},
            "found": {"index_id": current_index or None, "ir_id": current_ir or None},
            "credential_exposed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
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
                "Extract/generalize executor availability and freshness so Node online does not imply executor available.",
                "Preserve the credential-isolated executor-host boundary: executor hosts own no ONE transport credential.",
                "Reconcile executor lifecycle/bridge responsibilities with agentos.session-bridge/v0.1 without duplicate authority.",
                "Complete the remaining real client / vopc5750 acceptance required by #152 before closing the issue.",
                "Keep the verified Gemini -> ONE -> OpenAI Codex extension E3 slice under regression coverage.",
            ],
            "decisions_append": [
                "E3 Gemini extension -> ONE -> OpenAI Codex IDE extension continuity is VERIFIED from two independent fresh Codex threads given only 繼續.",
                "Both Codex threads resolved the same ONE_ACTIVE_CONTINUATION generation through one_resolve_active with credential_exposed=false.",
                "Client-specific bootstrap configuration contains discovery/runtime wiring only; Canonical IR remains the sole durable working state.",
                "The completed E3 slice does not close #152; broader Node/executor lifecycle extraction and real-client acceptance remain required.",
            ],
            "evidence": [
                {
                    "kind": "codex-extension-e3-pass-1",
                    "verdict": "PASS",
                    "summary": "Fresh Codex extension thread given only 繼續 resolved agentos-core idx-core-152-e3-codex-ext-1 / ir-core-152-e3-codex-ext-1 through ONE_ACTIVE_CONTINUATION.",
                    "date": "2026-09-02",
                    "issue_comment_id": "5503435564",
                },
                {
                    "kind": "codex-extension-e3-pass-2",
                    "verdict": "PASS",
                    "summary": "Second independent fresh Codex extension thread repeated the same bounded ONE resolution; terminal receipt recorded 2026-09-02T02:32:25Z.",
                    "date": "2026-09-02",
                    "issue_comment_id": "5503469931",
                    "evidence_path": ".agentos/evidence/issue-152-codex-extension-e3-verified-2026-09-02.md",
                },
            ],
            "execution_status": "in_progress",
            "execution_metadata": {
                "issue": "#152",
                "phase": "post-E3-node-executor-extraction",
                "e3_verdict": "VERIFIED",
            },
        },
        data_root=root,
    )
    activation = _activate(root)
    print(json.dumps({
        "schema": "agentos.issue-152-post-e3/v1",
        "ok": True,
        "advanced": True,
        "project_id": PROJECT_ID,
        "parent": {"index_id": EXPECTED_INDEX, "ir_id": EXPECTED_IR},
        "child": {"index_id": NEW_INDEX, "ir_id": NEW_IR},
        "active_selector": activation,
        "credential_exposed": False,
        "handoff_receipt": receipt,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
