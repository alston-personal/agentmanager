from __future__ import annotations

import json
import sys
from typing import Any

from agent_core.active_continuation import read_active_continuation
from agentos_node.one_mcp import OracleLocalGateway

HOOK_SCHEMA = "agentos.antigravity-one-preinvocation/v0.5"
SOURCE = "ONE_PREINVOCATION_IR"
IR_SCHEMA = "agentos.ir/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"


def _executor_identity(model_name: Any) -> tuple[str, bool]:
    """Bind only identities that the PreInvocation caller context can prove."""
    normalized = str(model_name or "").strip().casefold()
    if "codex" in normalized:
        return "antigravity-codex", True
    if "gemini" in normalized:
        return "antigravity-gemini", True
    return "antigravity-unknown", False


def _canonical_ir_from_resolution(
    result: dict[str, Any], *, expected_project_id: str
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if result.get("schema") != "agentos.resolve/v1":
        raise ValueError("unexpected ONE resolve schema")

    project = result.get("project") if isinstance(result.get("project"), dict) else {}
    if str(project.get("id") or "") != expected_project_id:
        raise ValueError("ONE resolved a project different from the active continuation selector")

    execution_head = result.get("execution_head")
    if not isinstance(execution_head, dict) or execution_head.get("schema") != EXECUTION_HEAD_SCHEMA:
        raise ValueError("canonical execution head is unavailable or has unsupported schema")

    continuation = result.get("continuation")
    if not isinstance(continuation, dict):
        raise ValueError("canonical continuation is unavailable")
    canonical_ir = continuation.get("canonical_ir")
    if not isinstance(canonical_ir, dict) or canonical_ir.get("schema_version") != IR_SCHEMA:
        raise ValueError("canonical continuation does not contain agentos.ir/v1")

    head_index = str(execution_head.get("index_id") or "").strip()
    ir_index = str(canonical_ir.get("index_id") or "").strip()
    if not head_index or head_index != ir_index:
        raise ValueError("canonical execution-head / IR index generation mismatch")
    if not str(canonical_ir.get("ir_id") or "").strip():
        raise ValueError("canonical IR has no ir_id")

    return execution_head, canonical_ir, head_index


def _compact_ir(
    result: dict[str, Any],
    execution_head: dict[str, Any],
    canonical_ir: dict[str, Any],
    index_id: str,
) -> dict[str, Any]:
    project = result.get("project") if isinstance(result.get("project"), dict) else {}
    continuation = canonical_ir.get("continuation") if isinstance(canonical_ir.get("continuation"), dict) else {}
    return {
        "schema_version": canonical_ir.get("schema_version"),
        "index_id": index_id,
        "ir_id": canonical_ir.get("ir_id"),
        "parent_ir_id": canonical_ir.get("parent_ir_id"),
        "project_id": project.get("id"),
        "goal": canonical_ir.get("goal"),
        "constraints": canonical_ir.get("constraints") or [],
        "decisions": canonical_ir.get("decisions") or [],
        "pending_tasks": canonical_ir.get("pending_tasks") or [],
        "continuation": continuation,
        "capability": canonical_ir.get("capability"),
        "next_action": (
            result.get("next_action")
            or continuation.get("recommended_action")
            or continuation.get("next_action")
        ),
        "mutation_allowed": bool(result.get("mutation_allowed")),
        "execution_head": {
            "schema": execution_head.get("schema"),
            "index_id": execution_head.get("index_id"),
            "active_goal": execution_head.get("active_goal"),
            "status": (
                execution_head.get("execution_head", {}).get("status")
                if isinstance(execution_head.get("execution_head"), dict)
                else None
            ),
        },
        "provenance": result.get("provenance") or {},
    }


def build_injection(
    payload: dict[str, Any],
    gateway: OracleLocalGateway | None = None,
    *,
    selector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Hydrate exactly once per fresh conversation. The authoritative project is
    # selected by ONE state, never by the IDE's current workspace path.
    if int(payload.get("invocationNum") or 0) != 0:
        return {}

    one = gateway or OracleLocalGateway()
    status = one.status()
    if not status.get("connected"):
        raise RuntimeError("ONE is not connected")

    active = selector or read_active_continuation(one.data_root)
    project_id = str(active.get("project_id") or "").strip()
    selector_index = str(active.get("index_id") or "").strip()
    selector_ir = str(active.get("ir_id") or "").strip()
    if not all((project_id, selector_index, selector_ir)):
        raise ValueError("ONE active continuation selector is incomplete")

    result = one.resolve(project_id)
    execution_head, canonical_ir, index_id = _canonical_ir_from_resolution(
        result, expected_project_id=project_id
    )
    canonical_ir_id = str(canonical_ir.get("ir_id") or "").strip()
    if index_id != selector_index or canonical_ir_id != selector_ir:
        raise ValueError(
            "ONE active continuation selector is stale: "
            f"selector={selector_index}/{selector_ir} "
            f"canonical={index_id}/{canonical_ir_id}"
        )

    ir = _compact_ir(result, execution_head, canonical_ir, index_id)
    executor_class, identity_bound = _executor_identity(payload.get("modelName"))

    envelope = {
        "schema": HOOK_SCHEMA,
        "source": SOURCE,
        "selection_source": "ONE_ACTIVE_CONTINUATION",
        "active_selector": {
            "project_id": project_id,
            "index_id": selector_index,
            "ir_id": selector_ir,
        },
        "status_schema": status.get("schema"),
        "connected": True,
        "realm_id": status.get("realm_id"),
        "node_id": status.get("node_id"),
        "surface": "antigravity",
        "executor_class": executor_class,
        "executor_identity_bound": identity_bound,
        "executor_identity_source": "preinvocation-modelName",
        "model_name": payload.get("modelName"),
        "credential_exposed": False,
        "canonical_ir": ir,
    }
    message = (
        "AgentOS ONE canonical IR hydration. ONE_ACTIVE_CONTINUATION selected this "
        "continuation before the model was called. The IDE workspace path is not "
        "a continuation authority and must not replace this state. Do not replace "
        "the Canonical IR with workspace enumeration, Pulse/PM2 scans, local-memory "
        "reconstruction, or vendor history. Newer explicit user intent still wins. "
        "Continue from canonical_ir.goal / pending_tasks / continuation / next_action "
        "and obey mutation_allowed. When reporting bootstrap provenance, state "
        "source=ONE_PREINVOCATION_IR, selection_source=ONE_ACTIVE_CONTINUATION, and "
        "include project_id + index_id + ir_id + executor_class + model_name. If "
        "executor_identity_bound=false, do not guess the executor identity.\n"
        + json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    )
    return {"injectSteps": [{"ephemeralMessage": message}]}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        output = build_injection(payload)
    except Exception as exc:
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": (
                        "ONE_IR_HEAD_UNRESOLVED: AgentOS canonical IR hydration "
                        f"failed: {type(exc).__name__}: {exc}. Do not claim or "
                        "reconstruct AgentOS continuation from workspace lists, "
                        "Pulse, PM2, local memory, or vendor history. Ask for/restore "
                        "the ONE active continuation selector/canonical IR head instead."
                    )
                }
            ]
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
