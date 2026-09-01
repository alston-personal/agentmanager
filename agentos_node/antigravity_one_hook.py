from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from agentos_node.one_mcp import OracleLocalGateway

HOOK_SCHEMA = "agentos.antigravity-one-preinvocation/v0.4"
SOURCE = "ONE_PREINVOCATION_IR"
CORE_PROJECT_ID = "agentos-core"
IR_SCHEMA = "agentos.ir/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"
DEFAULT_CORE_REPO_ROOT = "/home/ubuntu/agentmanager"


def _workspace_paths(raw_paths: Any) -> list[str]:
    if not isinstance(raw_paths, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_paths:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _core_repo_root() -> Path:
    return Path(
        os.environ.get("AGENTOS_CORE_REPO_ROOT", DEFAULT_CORE_REPO_ROOT)
    ).expanduser().resolve(strict=False)


def _core_workspace_present(paths: list[str]) -> bool:
    """Use Antigravity workspace metadata only as a Core bootstrap gate.

    A fresh Antigravity conversation may be opened at the repository root or at
    a descendant workspace such as ``agentmanager/workspace/if-tv-station``.
    Both belong to the same canonical Core checkout boundary for the #152
    acceptance slice.  Descendant names are never project selectors: once the
    gate is satisfied, continuation still resolves exactly ``agentos-core``.

    Paths that merely share a textual prefix with the Core checkout (for
    example ``/home/ubuntu/agentmanager-old``) are not accepted.
    """
    root = _core_repo_root()
    for value in paths:
        candidate = Path(value).expanduser().resolve(strict=False)
        if candidate == root or root in candidate.parents:
            return True
    return False


def _executor_identity(model_name: Any) -> tuple[str, bool]:
    """Bind only identities that the PreInvocation caller context can prove.

    The generic MCP server cannot know which IDE executor invoked a tool.  The
    Antigravity PreInvocation payload does include the current modelName, so the
    hook is the narrow layer that may bind a Gemini/Codex executor class.  Do not
    guess an identity from generic GPT/model-family names.
    """
    normalized = str(model_name or "").strip().casefold()
    if "codex" in normalized:
        return "antigravity-codex", True
    if "gemini" in normalized:
        return "antigravity-gemini", True
    return "antigravity-unknown", False


def _canonical_ir_from_resolution(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    if result.get("schema") != "agentos.resolve/v1":
        raise ValueError("unexpected ONE resolve schema")

    project = result.get("project") if isinstance(result.get("project"), dict) else {}
    if str(project.get("id") or "") != CORE_PROJECT_ID:
        raise ValueError("ONE did not resolve canonical agentos-core")

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


def build_injection(payload: dict[str, Any], gateway: OracleLocalGateway | None = None) -> dict[str, Any]:
    # Hydrate exactly once per fresh conversation.  The injected IR remains in
    # the trajectory for later turns, avoiding repeated context/token overhead.
    if int(payload.get("invocationNum") or 0) != 0:
        return {}

    paths = _workspace_paths(payload.get("workspacePaths"))
    if not _core_workspace_present(paths):
        # Global hook remains silent outside the canonical Core checkout tree.
        # Workspace descendants are only a gate; their names never choose state.
        return {}

    one = gateway or OracleLocalGateway()
    status = one.status()
    if not status.get("connected"):
        raise RuntimeError("ONE is not connected")

    # The existing canonical continuation publisher is restricted to
    # agentos-core.  Resolve that authoritative IR directly; do not infer state
    # from workspace order, Pulse, PM2, memory, or sibling repositories.
    result = one.resolve(CORE_PROJECT_ID)
    execution_head, canonical_ir, index_id = _canonical_ir_from_resolution(result)
    ir = _compact_ir(result, execution_head, canonical_ir, index_id)
    executor_class, identity_bound = _executor_identity(payload.get("modelName"))

    envelope = {
        "schema": HOOK_SCHEMA,
        "source": SOURCE,
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
        "AgentOS ONE canonical IR hydration. This is the single authoritative "
        "agentos-core continuation selected before the model was called. Do not "
        "replace it with workspace enumeration, Pulse/PM2 scans, local-memory "
        "reconstruction, or sibling project state. Newer explicit user intent "
        "still wins. Continue from canonical_ir.goal / pending_tasks / "
        "continuation / next_action and obey mutation_allowed. When reporting "
        "bootstrap provenance, state source=ONE_PREINVOCATION_IR and include "
        "index_id + ir_id + executor_class + model_name. If "
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
        # Fail closed for AgentOS continuity: Antigravity itself may continue,
        # but the model receives an explicit prohibition against claiming ONE
        # state from local reconstruction.
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": (
                        "ONE_IR_HEAD_UNRESOLVED: AgentOS canonical IR hydration "
                        f"failed: {type(exc).__name__}: {exc}. Do not claim or "
                        "reconstruct AgentOS continuation from workspace lists, "
                        "Pulse, PM2, or local memory. Ask for/restore the canonical "
                        "IR head instead."
                    )
                }
            ]
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
