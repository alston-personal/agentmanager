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
from agentos_node.ir_stop_sync import handle_stop_payload, is_stop_payload
from agentos_node.one_mcp import OneGatewayError, OracleLocalGateway

HOOK_SCHEMA = "agentos.antigravity-one-preinvocation/v0.6"
AUDIT_SCHEMA = "agentos.antigravity-preinvocation-attestation/v1"
SOURCE = "ONE_PREINVOCATION_IR"
IR_SCHEMA = "agentos.ir/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"
YELLOW_CONTEXT_TOKENS = 60_000
RED_CONTEXT_TOKENS = 100_000


def _inspect_transcript(transcript_path: Any) -> tuple[bool, bool, int]:
    """Return (readable, hydrated_since_checkpoint, latest_context_tokens)."""
    raw_path = str(transcript_path or "").strip()
    if not raw_path:
        return False, False, 0
    path = Path(raw_path).expanduser()
    if not path.is_file():
        return False, False, 0
    hydrated_since_checkpoint = False
    latest_tokens = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(step, dict):
                    continue
                step_type = str(step.get("type") or "")
                if step_type == "CHECKPOINT":
                    hydrated_since_checkpoint = False
                    latest_tokens = 0
                    continue
                if step_type in ("EPHEMERAL_MESSAGE", "SYSTEM_MESSAGE") or "ephemeralMessage" in step:
                    content = str(step.get("content") or step.get("ephemeralMessage") or "")
                    if SOURCE in content:
                        hydrated_since_checkpoint = True
                if step_type == "PLANNER_RESPONSE":
                    usage = (
                        step.get("model_usage")
                        if isinstance(step.get("model_usage"), dict)
                        else {}
                    )
                    try:
                        inp = int(usage.get("input_tokens") or step.get("input_tokens") or 0)
                        cache = int(usage.get("cache_read_tokens") or step.get("cache_read_tokens") or 0)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if inp + cache > 0:
                        latest_tokens = inp + cache
    except OSError:
        return False, False, 0
    return True, hydrated_since_checkpoint, latest_tokens


def _build_budget_guard_step(tokens: int) -> dict[str, Any] | None:
    iron_laws = (
        " Enforce the 3 Multi-Agent Budget Iron Laws: "
        "(1) One-Pending-Task-Per-Turn: execute ONLY pending_tasks[0] in a single turn; "
        "(2) One-Shot Subagent Only (No Followup Ping-Pong): spawn at most 1 one-shot invoke_subagent with a self-contained prompt and NEVER send followup send_message tasks to an existing subagent; "
        "(3) Coordinator-Only When Delegating: never run duplicate shell commands, file searches, or test suites in the parent thread."
    )
    if tokens >= RED_CONTEXT_TOKENS:
        return {
            "systemMessage": {
                "systemMessage": (
                    f"CONTEXT_BUDGET_GUARD: CRITICAL! Current context is {tokens} tokens "
                    "(>= 100,000 Red Zone). Strictly use invoke_subagent for any multi-step "
                    "work or keep tool calls minimal, and remind the user to run `/compact` "
                    "(without trailing spaces) or open a new window."
                    + iron_laws
                ),
                "metadata": {
                    "user_markdown": (
                        f"🚨 **Context 紅燈警戒 ({tokens:,} tokens)**：單次呼叫成本過高！"
                        "強烈建議立即輸入 `/compact`（請勿包含尾部空白）或開啟新對話視窗"
                        "（AgentOS ONE 將自動延續狀態）。本輪已強制啟用 Subagent 最小化模式（一輪一事、即用即棄）。"
                    )
                },
            }
        }
    if tokens >= YELLOW_CONTEXT_TOKENS:
        return {
            "systemMessage": {
                "systemMessage": (
                    f"CONTEXT_BUDGET_GUARD: Current context is {tokens} tokens. "
                    "Delegate any multi-step investigation or code modification (>3 tool calls) "
                    "to invoke_subagent so the main conversation context does not grow."
                    + iron_laws
                ),
                "metadata": {
                    "user_markdown": (
                        f"⚠️ **Context 水位預警 ({tokens:,} tokens)**："
                        "已自動啟用 Subagent 分流模式（一輪一事、子代理即用即棄）；建議適時輸入 `/compact`（勿加空白）。"
                    )
                },
            }
        }
    return None


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


def _safe_failure_code(exc: Exception) -> str:
    """Map failures to bounded model-visible codes without echoing details."""
    if isinstance(exc, OneGatewayError):
        value = str(exc).strip()
        return value[:96] if value else "one_gateway_error"
    if isinstance(exc, (FileNotFoundError, KeyError)):
        return "one_hydration_state_missing"
    if isinstance(exc, ValueError):
        return "one_hydration_validation_failed"
    if isinstance(exc, RuntimeError):
        return "one_hydration_runtime_failed"
    return "one_hydration_internal_error"


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
    # Hydrate once per fresh conversation or once after a /compact CHECKPOINT.
    # On subsequent user turns, only evaluate the Context Budget Gatekeeper.
    if int(payload.get("invocationNum") or 0) != 0:
        return {}

    readable, hydrated_since_checkpoint, latest_tokens = _inspect_transcript(
        payload.get("transcriptPath")
    )
    if readable:
        needs_hydration = not hydrated_since_checkpoint
    else:
        needs_hydration = int(payload.get("initialNumSteps") or 0) <= 1

    budget_step = _build_budget_guard_step(latest_tokens)
    if not needs_hydration:
        return {"injectSteps": [budget_step]} if budget_step else {}

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
        "and obey mutation_allowed. Enforce the Three Multi-Agent Budget Iron Laws: "
        "(1) One-Pending-Task-Per-Turn: execute ONLY pending_tasks[0] in a single turn unless explicitly asked otherwise; "
        "(2) One-Shot Subagent Only (No Followup Ping-Pong): delegate >4-step work to at most 1 one-shot invoke_subagent with a self-contained prompt and NEVER send followup send_message rounds to an existing subagent; "
        "(3) Coordinator-Only When Delegating: do not run duplicate shell commands, file searches, or test suites in the main thread while a subagent executes. "
        "When reporting bootstrap provenance, state "
        "source=ONE_PREINVOCATION_IR, selection_source=ONE_ACTIVE_CONTINUATION, and "
        "include project_id + index_id + ir_id + executor_class + model_name. If "
        "executor_identity_bound=false, do not guess the executor identity.\n"
        + json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    )
    inject_steps: list[dict[str, Any]] = [{"ephemeralMessage": message}]
    if budget_step:
        inject_steps.append(budget_step)
    return {"injectSteps": inject_steps}


def main() -> int:
    payload: dict[str, Any] = {}
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        if is_stop_payload(payload):
            output = handle_stop_payload(payload)
            json.dump(output, sys.stdout, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0
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
        if int(payload.get("invocationNum") or 0) == 0 and envelope is not None:
            _write_attestation(payload, envelope, outcome="hydrated")
    except Exception as exc:
        try:
            _write_attestation(payload, None, outcome="fail-closed")
        except Exception:
            pass
        code = _safe_failure_code(exc)
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": (
                        "ONE_IR_HEAD_UNRESOLVED: AgentOS canonical IR hydration "
                        f"failed (code={code}). Do not claim or reconstruct AgentOS "
                        "continuation from workspace lists, Pulse, PM2, local memory, "
                        "or vendor history. Ask for/restore the ONE active continuation "
                        "selector/canonical IR head instead."
                    )
                }
            ]
        }
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
