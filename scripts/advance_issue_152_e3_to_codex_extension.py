#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.active_continuation import activate_continuation
from agent_core.canonical_ir_handoff import advance_canonical_ir
from agent_core.resolve_facade import resolve_continuation

PROJECT_ID = "agentos-core"
EXPECTED_INDEX = "idx-core-152-e3-1"
EXPECTED_IR = "ir-core-152-e3-1"
NEW_INDEX = "idx-core-152-e3-codex-ext-1"
NEW_IR = "ir-core-152-e3-codex-ext-1"
GOAL = (
    "Prove E3 cross-extension continuity: Antigravity Gemini -> AgentOS ONE -> a completely fresh "
    "OpenAI Codex IDE extension thread continues from the authoritative Canonical IR without copied vendor history."
)
NEXT_ACTION = (
    "Install/reload the OpenAI Codex ONE bootstrap, then open a completely fresh Codex IDE extension thread "
    "and send only '繼續'; Codex must call agentos-one.one_resolve_active before workspace reconstruction, report "
    "source=ONE_ACTIVE_CONTINUATION, project=agentos-core, index_id=idx-core-152-e3-codex-ext-1, "
    "ir_id=ir-core-152-e3-codex-ext-1, and continue this cross-extension E3 goal."
)


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _activate(root: Path) -> dict:
    return activate_continuation(
        PROJECT_ID,
        index_id=NEW_INDEX,
        ir_id=NEW_IR,
        reason="#152 E3 corrected boundary: OpenAI Codex IDE extension is the active target executor",
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
            "schema": "agentos.issue-152-e3-codex-extension/v1",
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
            "schema": "agentos.issue-152-e3-codex-extension/v1",
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
                "Install the AgentOS ONE bootstrap into the OpenAI Codex local harness without copying Canonical IR into Codex config.",
                "Reload the Codex IDE extension, open a completely fresh thread, and send only '繼續'.",
                "Verify Codex resolves the ONE active continuation and reports the corrected E3 child generation before touching workspace-local continuation state.",
                "Repeat a second completely fresh Codex extension thread after the first pass before marking the cross-extension slice stable.",
                "Persist sanitized Codex extension evidence and update #152 without closing the broader Node/executor extraction issue.",
            ],
            "decisions_append": [
                "OpenAI Codex is a separate IDE extension/client from the Gemini/Antigravity extension; Gemini ~/.gemini PreInvocation hooks are not Codex lifecycle hooks.",
                "E3 acceptance is cross-extension continuity, not an expectation that Codex triggers Gemini's PreInvocation hook.",
                "Codex receives Canonical IR through its own native bootstrap surfaces: Codex AGENTS.md instructions plus the AgentOS ONE MCP adapter.",
                "Canonical IR remains the sole durable working state; Codex configuration contains only bootstrap/discovery instructions and no copied IR body.",
            ],
            "evidence": [
                {
                    "kind": "codex-preinvocation-boundary-correction",
                    "verdict": "VERIFIED_ARCHITECTURE_FINDING",
                    "summary": "Fresh Codex attempts did not update the Gemini PreInvocation attestation; the retained receipt remained the prior Gemini invocation, proving the two extension lifecycles must be handled separately.",
                    "date": "2026-09-02",
                },
                {
                    "kind": "gemini-e3-selector-hydration",
                    "verdict": "PASS",
                    "summary": "Gemini PreInvocation successfully hydrated agentos-core through ONE_ACTIVE_CONTINUATION with idx-core-152-e3-1 / ir-core-152-e3-1 and credential_exposed=false.",
                    "date": "2026-09-02",
                },
            ],
            "execution_status": "in_progress",
            "execution_metadata": {
                "issue": "#152",
                "phase": "E3-openai-codex-extension-continuity",
                "previous_phase": "E3-antigravity-codex-continuity",
            },
        },
        data_root=root,
    )
    activation = _activate(root)
    print(json.dumps({
        "schema": "agentos.issue-152-e3-codex-extension/v1",
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
