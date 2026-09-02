from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.active_continuation import read_active_continuation
from agentos_node.one_mcp import OracleLocalGateway

HOOK_SCHEMA = "agentos.antigravity-one-preinvocation/v0.6"
AUDIT_SCHEMA = "agentos.antigravity-preinvocation-attestation/v1"
SOURCE = "ONE_PREINVOCATION_IR"
IR_SCHEMA = "agentos.ir/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _audit_path() -> Path:
    explicit = str(os.environ.get("AGENTOS_PREINVOCATION_AUDIT_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    return root / "runtime" / "antigravity-preinvocation-last.json"


def _conversation_hash(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _runtime_source_commit() -> str | None:
    explicit = str(os.environ.get("AGENTOS_RUNTIME_SOURCE_COMMIT") or "").strip()
    if explicit:
        return explicit
    candidate = Path(__file__).resolve().parents[1].name
    return candidate if len(candidate) >= 12 else None


def _write_attestation(payload: dict[str, Any], envelope: dict[str, Any] | None, *, outcome: str) -> None:
    if int(payload.get("invocationNum") or 0) != 0:
        return
    executor_class, identity_bound = _executor_identity(payload.get("modelName"))
    selector = envelope.get("active_selector") if isinstance(envelope, dict) and isinstance(envelope.get("active_selector"), dict) else {}
    record = {
        "schema": AUDIT_SCHEMA,
        "recorded_at": _now(),
        "runtime_source_commit": _runtime_source_commit(),
        "hook_schema": HOOK_SCHEMA,
        "outcome": outcome,
        "invocation_num": 0,
        "conversation_id_sha256": _conversation_hash(payload.get("conversationId")),
        "model_name": payload.get("modelName"),
        "executor_class": (envelope or {}).get("executor_class") or executor_class,
        "executor_identity_bound": (envelope or {}).get("executor_identity_bound") if isinstance(envelope, dict) else identity_bound,
        "injection_emitted": outcome == "hydrated",
        "source": (envelope or {}).get("source"),
        "selection_source": (envelope or {}).get("selection_source"),
        "project_id": selector.get("project_id"),
        "index_id": selector.get("index_id"),
        "ir_id": selector.get("ir_id"),
        "credential_exposed": False,
    }
    path = _audit_path()
    if path.is_symlink():
        raise ValueError("PreInvocation attestation path may not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".antigravity-preinvocation-", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            json.dump(record, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = None
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


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
    payload: dict[str, Any] = {}
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        output = build_injection(payload)
        envelope: dict[str, Any] | None = None
        steps = output.get("injectSteps") if isinstance(output, dict) else None
        if isinstance(steps, list) and steps:
            message = str((steps[0] or {}).get("ephemeralMessage") or "")
            if "\n" in message:
                try:
                    parsed = json.loads(message.rsplit("\n", 1)[-1])
                    envelope = parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    envelope = None
        if int(payload.get("invocationNum") or 0) == 0:
            _write_attestation(payload, envelope, outcome="hydrated" if envelope else "no-injection")
    except Exception as exc:
        try:
            _write_attestation(payload, None, outcome="fail-closed")
        except Exception:
            pass
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
