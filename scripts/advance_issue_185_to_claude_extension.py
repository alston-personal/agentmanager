#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from agent_core.active_continuation import activate_continuation, resolve_active_continuation
from agent_core.canonical_ir_handoff import advance_canonical_ir

PROJECT_ID = "agentos-core"
NEW_INDEX = "idx-core-185-claude-ext-1"
NEW_IR = "ir-core-185-claude-ext-1"
GOAL = (
    "Prove Anthropic Claude Code IDE extension -> AgentOS ONE continuity with a local/unknown backend identity kept "
    "separate from the Anthropic extension surface, using completely fresh extension threads and no copied vendor history."
)
NEXT_ACTION = (
    "Install/reload the Claude Code ONE bootstrap, then open a completely fresh Claude Code extension thread and send only "
    "'繼續'; Claude must call agentos-one.one_resolve_active before workspace reconstruction, report "
    "source=ONE_ACTIVE_CONTINUATION with project=agentos-core, index_id=idx-core-185-claude-ext-1, "
    "ir_id=ir-core-185-claude-ext-1, preserve backend identity uncertainty, and continue this #185 goal."
)


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required for exact-parent handoff")
    return value


def _activate(root: Path) -> dict:
    return activate_continuation(
        PROJECT_ID,
        index_id=NEW_INDEX,
        ir_id=NEW_IR,
        reason="#185 Claude Code extension continuity acceptance target",
        data_root=root,
    )


def main() -> int:
    root = _data_root()
    expected_index = _required("AGENTOS_EXPECTED_PARENT_INDEX")
    expected_ir = _required("AGENTOS_EXPECTED_PARENT_IR")
    active = resolve_active_continuation(data_root=root)
    selector = active.get("selector") if isinstance(active.get("selector"), dict) else {}
    current_project = str(selector.get("project_id") or "").strip()
    current_index = str(selector.get("index_id") or "").strip()
    current_ir = str(selector.get("ir_id") or "").strip()

    if current_project != PROJECT_ID:
        print(json.dumps({
            "schema": "agentos.issue-185-claude-extension-handoff/v1",
            "ok": False,
            "advanced": False,
            "reason": "active project is not agentos-core; refusing cross-project overwrite",
            "found": {"project_id": current_project or None, "index_id": current_index or None, "ir_id": current_ir or None},
            "credential_exposed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    if current_index == NEW_INDEX and current_ir == NEW_IR:
        activation = _activate(root)
        print(json.dumps({
            "schema": "agentos.issue-185-claude-extension-handoff/v1",
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

    if current_index != expected_index or current_ir != expected_ir:
        print(json.dumps({
            "schema": "agentos.issue-185-claude-extension-handoff/v1",
            "ok": False,
            "advanced": False,
            "reason": "unexpected canonical parent; refusing to overwrite",
            "expected": {"index_id": expected_index, "ir_id": expected_ir},
            "found": {"index_id": current_index or None, "ir_id": current_ir or None},
            "credential_exposed": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    receipt = advance_canonical_ir(
        {
            "project_id": PROJECT_ID,
            "expected_index_id": expected_index,
            "expected_ir_id": expected_ir,
            "new_index_id": NEW_INDEX,
            "new_ir_id": NEW_IR,
            "goal": GOAL,
            "next_action": NEXT_ACTION,
            "pending_tasks": [
                "Install the Claude Code user-scope AgentOS ONE MCP and managed user CLAUDE.md bootstrap without copying Canonical IR or Realm credentials.",
                "Reload/open a completely fresh Claude Code IDE extension thread and send only '繼續'.",
                "Require ONE_ACTIVE_CONTINUATION resolution of idx-core-185-claude-ext-1 / ir-core-185-claude-ext-1 before workspace/local-history reconstruction.",
                "Inspect the independent Node-local Claude ONE receipt and require credential_exposed=false plus explicit surface/executor/backend identity separation.",
                "Repeat a second completely fresh Claude Code extension thread with a newer receipt before marking #185 continuity VERIFIED.",
                "After continuity is verified, hand the Claude-extension/local-backend surface to #117 for separate Experience A/B regression.",
            ],
            "decisions_append": [
                "Claude Code extension continuity reuses ONE active selector + Canonical IR; it does not create a Claude-specific state protocol.",
                "Claude Code uses its native user CLAUDE.md plus user-scope stdio MCP bootstrap; Gemini PreInvocation and Codex AGENTS semantics are not assumed.",
                "Anthropic extension surface identity must not imply backend/model=Claude. Backend identity is recorded only from explicit trusted-local configuration; otherwise it remains unbound/unknown.",
                "Realm/node credentials remain inside the trusted Node-local ONE runtime and are not copied into Claude settings or receipts.",
            ],
            "evidence": [
                {
                    "kind": "claude-extension-bootstrap-contract",
                    "verdict": "STATIC_CANDIDATE",
                    "summary": "#185 branch defines user CLAUDE.md + user-scope stdio MCP bootstrap, identity separation, sanitized receipt, and hosted contract tests; live fresh-session proof remains pending.",
                    "date": "2026-09-02",
                }
            ],
            "execution_status": "in_progress",
            "execution_metadata": {"issue": "#185", "phase": "claude-extension-one-continuity"},
        },
        data_root=root,
    )
    activation = _activate(root)
    print(json.dumps({
        "schema": "agentos.issue-185-claude-extension-handoff/v1",
        "ok": True,
        "advanced": True,
        "project_id": PROJECT_ID,
        "parent": {"index_id": expected_index, "ir_id": expected_ir},
        "child": {"index_id": NEW_INDEX, "ir_id": NEW_IR},
        "active_selector": activation,
        "credential_exposed": False,
        "handoff_receipt": receipt,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
