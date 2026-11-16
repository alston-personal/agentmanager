from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.active_continuation import (
    activate_continuation,
    read_active_continuation,
)
from agent_core.canonical_ir_handoff import advance_canonical_ir
from agent_core.resolve_facade import resolve_continuation

STOP_SYNC_SCHEMA = "agentos.ir-stop-sync/v1"
TAIL_READ_BYTES = 65_536

_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>",
    re.DOTALL | re.IGNORECASE,
)
_METADATA_BLOCK_RE = re.compile(
    r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>",
    re.DOTALL | re.IGNORECASE,
)
_CONTEXT_SUMMARY_RE = re.compile(
    r"<CONTEXT_SUMMARY>.*?</CONTEXT_SUMMARY>",
    re.DOTALL | re.IGNORECASE,
)
_SECRET_REDACT_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,}|ghp_[A-Za-z0-9]{12,})"
)


def _now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clean_text(raw: Any, *, max_chars: int = 240) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = _METADATA_BLOCK_RE.sub("", text)
    text = _CONTEXT_SUMMARY_RE.sub("", text)
    match = _USER_REQUEST_RE.search(text)
    if match:
        text = match.group(1).strip()
    text = _SECRET_REDACT_RE.sub("[REDACTED]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def _is_ignorable_intent(text: str) -> bool:
    cleaned = text.strip().lower()
    if not cleaned:
        return True
    if cleaned in ("/compact", "compact"):
        return True
    return False


def _extract_claude_content(message_obj: Any) -> str:
    if isinstance(message_obj, str):
        return message_obj
    if isinstance(message_obj, dict):
        content = message_obj.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return " ".join(parts)
    return ""


def read_transcript_tail(
    transcript_path: Any,
    *,
    max_bytes: int = TAIL_READ_BYTES,
) -> tuple[str, str]:
    """Read tail of Antigravity or Claude JSONL transcript -> (user_intent, assistant_summary)."""
    raw_path = str(transcript_path or "").strip()
    if not raw_path:
        return "", ""
    path = Path(raw_path).expanduser()
    if not path.is_file():
        return "", ""

    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            chunk = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return "", ""

    lines = chunk.splitlines()
    if size > max_bytes and len(lines) > 1:
        # Drop potentially partial first line when seeking mid-file
        lines = lines[1:]

    latest_user = ""
    latest_assistant = ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue

        step_type = str(entry.get("type") or "")
        # Antigravity transcript format
        if step_type == "USER_INPUT":
            candidate = _clean_text(entry.get("content"), max_chars=200)
            if candidate and not _is_ignorable_intent(candidate):
                latest_user = candidate
        elif step_type == "PLANNER_RESPONSE":
            candidate = _clean_text(entry.get("content"), max_chars=240)
            if candidate:
                latest_assistant = candidate
        # Claude Code transcript format
        elif step_type == "user" or (
            isinstance(entry.get("message"), dict)
            and entry["message"].get("role") == "user"
        ):
            raw_msg = entry.get("message") if "message" in entry else entry
            candidate = _clean_text(_extract_claude_content(raw_msg), max_chars=200)
            if candidate and not _is_ignorable_intent(candidate):
                latest_user = candidate
        elif step_type == "assistant" or (
            isinstance(entry.get("message"), dict)
            and entry["message"].get("role") == "assistant"
        ):
            raw_msg = entry.get("message") if "message" in entry else entry
            candidate = _clean_text(_extract_claude_content(raw_msg), max_chars=240)
            if candidate:
                latest_assistant = candidate

    return latest_user, latest_assistant


def _write_stop_sync_audit(record: dict[str, Any], *, data_root: Path) -> None:
    try:
        runtime_dir = data_root / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        path = runtime_dir / "ir-stop-sync-last.json"
        if path.is_symlink():
            return
        fd, raw = tempfile.mkstemp(
            prefix=".ir-stop-sync-", suffix=".tmp", dir=str(runtime_dir)
        )
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
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    except Exception:
        pass


def advance_active_ir_checkpoint(
    *,
    surface: str,
    model_name: str,
    user_intent: str,
    assistant_summary: str,
    automatic: bool = False,
    explicit_next_action: str = "",
    explicit_decision: str = "",
    completed_tasks: list[str] | None = None,
    expected_project_id: str = "",
    expected_index_id: str = "",
    expected_ir_id: str = "",
    data_root: str | Path | None = None,
    governance_path: str | Path | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Advance canonical IR and active-continuation selector with CAS retry."""
    completed = [] if completed_tasks is None else completed_tasks
    if (not isinstance(completed, list) or len(completed) > 20
            or any(not isinstance(t, str) or not t.strip() or len(t) > 1000 for t in completed)
            or len(set(completed)) != len(completed)):
        raise ValueError("completed_tasks must contain at most 20 distinct exact task strings")
    semantic_change = bool(completed or explicit_next_action.strip() or explicit_decision.strip())
    if automatic and semantic_change:
        raise ValueError("automatic Stop cannot change task semantics")
    if semantic_change and not all((expected_project_id, expected_index_id, expected_ir_id)):
        raise ValueError("semantic changes require the observed project/index/IR generation")
    root = (
        Path(data_root)
        if data_root is not None
        else Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    )
    cleaned_user = _clean_text(user_intent, max_chars=160)
    cleaned_assistant = _clean_text(assistant_summary, max_chars=240)
    model_label = str(model_name or "unknown").strip() or "unknown"
    surface_label = str(surface or "unknown").strip() or "unknown"

    last_error: Exception | None = None
    for attempt in range(max(1, max_retries)):
        try:
            selector = read_active_continuation(root)
            project_id = str(selector["project_id"])

            current = resolve_continuation(
                project_id,
                governance_path=governance_path,
                data_root=root,
            )
            head = (
                current.get("execution_head")
                if isinstance(current.get("execution_head"), dict)
                else {}
            )
            cont = (
                current.get("continuation")
                if isinstance(current.get("continuation"), dict)
                else {}
            )
            ir = (
                cont.get("canonical_ir")
                if isinstance(cont.get("canonical_ir"), dict)
                else {}
            )

            expected_index = str(head.get("index_id") or "").strip()
            expected_ir = str(ir.get("ir_id") or "").strip()
            goal = str(
                ir.get("goal")
                or head.get("active_goal")
                or "Maintain AgentOS ONE cross-surface canonical IR continuity"
            ).strip()
            pending_tasks = list(ir.get("pending_tasks") or [])
            if semantic_change:
                if (project_id, expected_index, expected_ir) != (expected_project_id, expected_index_id, expected_ir_id):
                    raise ValueError("stale semantic change generation; resolve current IR before retrying")
            if completed:
                if any(task not in pending_tasks for task in completed):
                    raise ValueError("completed task is not in the observed pending list")
                pending_tasks = [task for task in pending_tasks if task not in completed]

            utc_ts = _now_utc_compact()
            seed = (
                f"{expected_index}:{expected_ir}:{surface_label}:{model_label}:"
                f"{cleaned_user}:{cleaned_assistant}:{time.time_ns()}:{attempt}"
            )
            short_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
            new_index_id = f"idx-core-{utc_ts}-{short_hash}"
            new_ir_id = f"ir_{utc_ts}_{short_hash}"

            if explicit_next_action.strip():
                next_action = _clean_text(explicit_next_action, max_chars=280)
            elif completed:
                next_action = _clean_text(pending_tasks[0], max_chars=280) if pending_tasks else "No pending tasks; verify goal acceptance or await new user intent."
            else:
                current_continuation = ir.get("continuation") or {}
                next_action = current_continuation.get("next_action") or current_continuation.get("recommended_action")
                if not isinstance(next_action, str) or not next_action.strip():
                    raise ValueError("current IR has no next action to preserve")

            if explicit_decision.strip():
                decision_line = _clean_text(explicit_decision, max_chars=220)
            else:
                decision_line = ""

            evidence_item = {
                "kind": "turn-checkpoint",
                "verdict": "RECORDED",
                "task_relevance": "NOT_EVALUATED",
                "summary": (
                    f"[{utc_ts}] ({surface_label}/{model_label}) "
                    f"intent='{cleaned_user[:80]}' result='{cleaned_assistant[:120]}'"
                ),
            }

            handoff_receipt = advance_canonical_ir(
                {
                    "project_id": project_id,
                    "expected_index_id": expected_index,
                    "expected_ir_id": expected_ir,
                    "new_index_id": new_index_id,
                    "new_ir_id": new_ir_id,
                    "goal": goal,
                    "next_action": next_action,
                    "pending_tasks": pending_tasks,
                    "decisions_append": [decision_line] if decision_line else [],
                    "evidence": [evidence_item],
                    "execution_status": (head.get("execution_head") or {}).get("status", "in_progress"),
                    "execution_metadata": {
                        "last_surface": surface_label,
                        "last_model": model_label,
                        "updated_by": "ir_stop_sync" if automatic else "one_checkpoint",
                    },
                },
                data_root=root,
                governance_path=governance_path,
            )
            activation = activate_continuation(
                project_id,
                index_id=new_index_id,
                ir_id=new_ir_id,
                reason=f"auto-sync:{surface_label}:{model_label}",
                data_root=root,
            )
            result = {
                "schema": STOP_SYNC_SCHEMA,
                "ok": True,
                "recorded_at": _now_iso(),
                "surface": surface_label,
                "model_name": model_label,
                "project_id": project_id,
                "previous": {"index_id": expected_index, "ir_id": expected_ir},
                "current": {"index_id": new_index_id, "ir_id": new_ir_id},
                "next_action": next_action,
                "completed_tasks": completed,
                "handoff": handoff_receipt,
                "activation": activation,
                "credential_exposed": False,
            }
            _write_stop_sync_audit(result, data_root=root)
            return result
        except Exception as exc:
            if semantic_change or automatic:
                # Never rebase a completion declaration onto a newer user's generation.
                raise
            last_error = exc
            continue

    raise RuntimeError(f"failed to advance canonical IR after retries: {last_error}")


def is_stop_payload(payload: dict[str, Any]) -> bool:
    """Detect whether stdin JSON payload is an Antigravity or Claude Code Stop hook event."""
    if "terminationReason" in payload or "executionNum" in payload:
        return True
    if str(payload.get("hook_event_name") or "").strip().lower() == "stop":
        return True
    if "session_id" in payload and "transcript_path" in payload and "invocationNum" not in payload:
        return True
    return False


def handle_stop_payload(
    payload: dict[str, Any],
    *,
    data_root: str | Path | None = None,
    governance_path: str | Path | None = None,
) -> dict[str, Any]:
    """Process a Stop hook payload fail-open and return the stdout response dict."""
    is_claude = (
        str(payload.get("hook_event_name") or "").strip().lower() == "stop"
        or ("session_id" in payload and "terminationReason" not in payload)
    )
    default_response: dict[str, Any] = {} if is_claude else {"decision": "allow"}

    try:
        if is_claude:
            if payload.get("stop_hook_active"):
                return default_response
            surface = "claude-code"
            model_name = str(payload.get("model") or os.environ.get("ANTHROPIC_MODEL") or "claude-code")
            transcript_path = payload.get("transcript_path")
            raw_last_input = payload.get("last_user_input") or ""
        else:
            termination_reason = str(payload.get("terminationReason") or "").strip()
            if termination_reason != "NO_TOOL_CALL":
                return default_response
            surface = "antigravity"
            model_name = str(payload.get("modelName") or "antigravity-unknown")
            transcript_path = payload.get("transcriptPath")
            raw_last_input = payload.get("lastUserInput") or ""

        tail_user, tail_assistant = read_transcript_tail(transcript_path)
        user_intent = _clean_text(raw_last_input, max_chars=200) or tail_user
        assistant_summary = tail_assistant

        if _is_ignorable_intent(user_intent) and not assistant_summary:
            return default_response
        if _is_ignorable_intent(user_intent) and str(raw_last_input or "").strip().lower() in ("/compact", "compact"):
            return default_response

        if not user_intent:
            user_intent = "continue active task"
        if not assistant_summary:
            assistant_summary = "completed turn response"

        advance_active_ir_checkpoint(
            surface=surface,
            model_name=model_name,
            user_intent=user_intent,
            assistant_summary=assistant_summary,
            automatic=True,
            data_root=data_root,
            governance_path=governance_path,
        )
    except Exception as exc:
        # Fail-open on stdout so chat UI never hangs on transient lock/IO error
        root = Path(data_root or os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
        _write_stop_sync_audit({"schema": STOP_SYNC_SCHEMA, "ok": False,
                              "recorded_at": _now_iso(), "error_type": type(exc).__name__,
                              "credential_exposed": False}, data_root=root)
        return default_response

    return default_response


def main() -> int:
    payload: dict[str, Any] = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
    except Exception:
        json.dump({"decision": "allow"}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    output = handle_stop_payload(payload)
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
