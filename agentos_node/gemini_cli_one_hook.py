from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from agent_core.active_continuation import read_active_continuation
from agentos_node.one_mcp import OracleLocalGateway, create_gateway

HOOK_SCHEMA = "agentos.gemini-cli-sessionstart/v0.1"
SOURCE = "ONE_SESSIONSTART_IR"


def _compact_context(result: dict[str, Any], selector: dict[str, Any]) -> dict[str, Any]:
    continuation = result.get("continuation") if isinstance(result.get("continuation"), dict) else {}
    canonical_ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
    execution_head = result.get("execution_head") if isinstance(result.get("execution_head"), dict) else {}
    project = result.get("project") if isinstance(result.get("project"), dict) else {}
    return {
        "schema": HOOK_SCHEMA,
        "source": SOURCE,
        "selection_source": "ONE_ACTIVE_CONTINUATION",
        "project_id": project.get("id"),
        "index_id": selector.get("index_id"),
        "ir_id": selector.get("ir_id"),
        "goal": canonical_ir.get("goal") or result.get("active_goal"),
        "constraints": canonical_ir.get("constraints") or [],
        "decisions": canonical_ir.get("decisions") or [],
        "pending_tasks": canonical_ir.get("pending_tasks") or [],
        "next_action": result.get("next_action"),
        "mutation_allowed": bool(result.get("mutation_allowed")),
        "credential_exposed": False,
        "surface": "gemini-cli",
        "executor_class": "gemini-cli",
        "execution_head": {
            "schema": execution_head.get("schema"),
            "index_id": execution_head.get("index_id"),
            "active_goal": execution_head.get("active_goal"),
        },
    }


def build_session_start(payload: dict[str, Any], *, gateway=None, selector=None) -> dict[str, Any]:
    if str(payload.get("hook_event_name") or "") not in {"", "SessionStart"}:
        return {}

    one = gateway or create_gateway()
    status = one.status()
    if not status.get("connected"):
        raise RuntimeError("one_not_connected")

    active = selector
    if active is None and isinstance(one, OracleLocalGateway):
        active = read_active_continuation(one.data_root)
    if active is None:
        project_id = str(os.environ.get("AGENTOS_ACTIVE_PROJECT") or "").strip()
        if not project_id:
            return {
                "systemMessage": "AgentOS ONE connected. Use the agentos-one MCP before reconstructing project state.",
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        "AgentOS ONE is connected through a credential-isolated MCP adapter. "
                        "For AgentOS work, call one_status and one_resolve(project) before substantial continuation. "
                        "Do not infer canonical state from vendor chat history. Newer explicit user intent wins."
                    ),
                },
            }
        result = one.resolve(project_id)
        continuation = result.get("continuation") if isinstance(result.get("continuation"), dict) else {}
        canonical_ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
        execution_head = result.get("execution_head") if isinstance(result.get("execution_head"), dict) else {}
        active = {
            "project_id": project_id,
            "index_id": execution_head.get("index_id") or canonical_ir.get("index_id"),
            "ir_id": canonical_ir.get("ir_id"),
        }

    project_id = str(active.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("active_project_missing")

    result = one.resolve(project_id)
    context = _compact_context(result, active)
    message = (
        "AgentOS ONE canonical continuation is authoritative for this AgentOS task. "
        "Do not replace it with workspace scanning or vendor history. Newer explicit user intent wins.\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
    )
    return {
        "systemMessage": f"AgentOS ONE hydrated: {project_id}",
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        },
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook_input_not_object")
        output = build_session_start(payload)
    except Exception:
        output = {
            "systemMessage": "AgentOS ONE hydration unavailable.",
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "ONE_IR_HEAD_UNRESOLVED. Do not claim AgentOS continuation from local workspace "
                    "or vendor history. Use the agentos-one MCP to restore canonical state."
                ),
            },
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
