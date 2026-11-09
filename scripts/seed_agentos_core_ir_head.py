#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_core.project_continuation_index import publish_project_continuation

PROJECT_ID = "agentos-core"
INDEX_ID = "idx-core-152-e2-bootstrap-v1"
IR_ID = "ir-core-152-e2-bootstrap-v1"
GOAL = (
    "Complete #152 Antigravity canonical IR hydration and prove that a fresh "
    "built-in Gemini session continues from AgentOS ONE without copied vendor history."
)
NEXT_ACTION = (
    "Re-run the Oracle Antigravity ONE bootstrap and require the pre-invocation probe "
    "to return ONE_PREINVOCATION_IR with matching execution-head and canonical IR index_id; "
    "then reload Antigravity and run a completely fresh Gemini regression using only '繼續'."
)


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def build_seed_payload() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "execution_head": {
            "schema": "agentos.execution-head/v1",
            "index_id": INDEX_ID,
            "active_goal": GOAL,
            "execution_head": {
                "status": "in_progress",
                "issue": "#152",
                "phase": "E2-antigravity-canonical-ir-hydration",
            },
        },
        "continuation": {
            "protocol": "ANCP/1.0",
            "index_id": INDEX_ID,
            "recommended_action": NEXT_ACTION,
            "canonical_ir": {
                "schema_version": "agentos.ir/v1",
                "index_id": INDEX_ID,
                "ir_id": IR_ID,
                "parent_ir_id": None,
                "goal": GOAL,
                "constraints": [
                    "The active Antigravity built-in Gemini executor is distinct from agy, standalone gemini, Claude, and Codex.",
                    "Workspace membership is only a hydration gate; workspace names must not select or reconstruct continuation state.",
                    "Canonical continuation must come from ONE agentos.ir/v1 and matching agentos.execution-head/v1 generation.",
                    "If the canonical IR head is missing, malformed, or generation-mismatched, fail closed instead of consulting Pulse, PM2, local memory, or vendor chat history as authority.",
                    "Realm/node credentials remain inside the trusted local adapter and are never model-visible.",
                    "Do not mutate protected main/master/release branches without a separate explicit human authorization event.",
                ],
                "decisions": [
                    "Use the existing project continuation publisher and index_id generation fence rather than introducing project-focus state.",
                    "For #152 Core acceptance, hydrate the authoritative agentos-core IR directly; sibling workspace projects are not continuation candidates.",
                    "Treat ONE_PREINVOCATION_IR as the primary fresh-session continuity source; newer explicit user intent still wins.",
                ],
                "pending_tasks": [
                    "Re-run Oracle bootstrap until preinvocation_hook_probe proves a valid canonical IR generation.",
                    "Reload Antigravity so the installed PreInvocation hook is active.",
                    "Open a completely fresh built-in Gemini conversation and send only '繼續'.",
                    "Capture a second completely fresh-session regression before marking E2 verified.",
                ],
                "continuation": {
                    "recommended_action": NEXT_ACTION,
                    "next_action": NEXT_ACTION,
                },
                "capability": "agentos.one.resolve",
            },
        },
    }


def main() -> int:
    root = _data_root()
    project_dir = root / "projects" / PROJECT_ID
    execution_path = project_dir / "execution-head.json"
    continuation_path = project_dir / "continuity" / "latest.json"

    existing = [str(path) for path in (execution_path, continuation_path) if path.exists()]
    if existing:
        print(
            json.dumps(
                {
                    "schema": "agentos.core-ir-seed/v1",
                    "ok": False,
                    "seeded": False,
                    "reason": "canonical head paths already exist; refusing migration overwrite",
                    "existing_paths": existing,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 3

    receipt = publish_project_continuation(build_seed_payload(), data_root=root)
    print(
        json.dumps(
            {
                "schema": "agentos.core-ir-seed/v1",
                "ok": True,
                "seeded": True,
                "project_id": PROJECT_ID,
                "index_id": INDEX_ID,
                "ir_id": IR_ID,
                "publish_receipt": receipt,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
