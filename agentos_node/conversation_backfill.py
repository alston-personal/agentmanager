"""Bounded, review-first recovery of historical conversation experience.

The backfill reads only approved summary artifacts from an explicitly supplied
conversation root. It never copies raw chats, browser scratchpads, attachments,
or credentials into a candidate. Promotion remains a separate governed step.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from agent_core.historical_ir import build_historical_ir, historical_ir_digest


SCHEMA = "agentos.conversation-experience-candidate/v1"
REPORT_SCHEMA = "agentos.conversation-backfill-report/v1"
SUMMARY_FILES = ("walkthrough.md", "task.md", "implementation_plan.md")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _candidate_id(project_id: str, conversation_id: str, digest: str) -> str:
    safe_project = re.sub(r"[^a-zA-Z0-9._-]", "-", project_id)
    safe_conversation = re.sub(r"[^a-zA-Z0-9._-]", "-", conversation_id)
    return f"conversation.{safe_project}.{safe_conversation}.{digest[:12]}"


def _signals(text: str) -> dict[str, int]:
    return {
        "pass_markers": len(re.findall(r"\bPASS\b", text, flags=re.I)),
        "fail_markers": len(re.findall(r"\bFAIL(?:ED)?\b", text, flags=re.I)),
        "completion_markers": len(re.findall(r"\b(?:completed|complete|done|完成)\b", text, flags=re.I)),
        "open_task_markers": len(re.findall(r"^\s*-\s*\[\s*\]", text, flags=re.M)),
    }


def _candidate(project_id: str, conversation: Path) -> dict[str, Any] | None:
    records: list[tuple[str, bytes]] = []
    signals = {"pass_markers": 0, "fail_markers": 0, "completion_markers": 0, "open_task_markers": 0}
    for name in SUMMARY_FILES:
        path = conversation / name
        if not path.is_file() or path.is_symlink():
            continue
        raw = path.read_bytes()
        records.append((name, raw))
        for key, value in _signals(raw.decode("utf-8", errors="replace")).items():
            signals[key] += value
    if not records:
        return None
    digest = sha256(b"".join(name.encode("utf-8") + b"\0" + raw for name, raw in records)).hexdigest()
    # A conversation without a concrete terminal signal stays out of the queue.
    if not (signals["pass_markers"] or signals["fail_markers"] or signals["completion_markers"]):
        return None
    conversation_id = conversation.name
    return {
        "schema": SCHEMA,
        "candidate_id": _candidate_id(project_id, conversation_id, digest),
        "project_id": project_id,
        "conversation_id": conversation_id,
        "source_digest": "sha256:" + digest,
        "source_files": [name for name, _ in records],
        "signals": signals,
        "status": "candidate",
        "promotion_required": True,
        "raw_conversation_copied": False,
        "credential_exposed": False,
    }


def _candidate_count(root: Path) -> int:
    if not root.is_dir() or root.is_symlink():
        return 0
    return sum(
        1
        for project in root.iterdir()
        if project.is_dir() and not project.is_symlink()
        for candidate in project.glob("*.json")
        if candidate.is_file() and not candidate.is_symlink()
    )


def backfill_conversation_candidates(
    *,
    projects_root: Path,
    candidate_root: Path,
    historical_ir_root: Path | None = None,
    max_conversations: int = 100,
) -> dict[str, Any]:
    """Recover bounded candidates from ``<project>/logs/conversations/<id>``.

    Enumeration is deliberately fixed-depth and limited; it does not recurse
    through conversation attachments or arbitrary workspace paths.
    """
    projects_root = Path(projects_root)
    candidate_root = Path(candidate_root)
    historical_ir_root = Path(historical_ir_root) if historical_ir_root is not None else candidate_root.parent / "historical-ir"
    if max_conversations < 1 or max_conversations > 500:
        raise ValueError("max_conversations must be between 1 and 500")
    before_candidate_count = _candidate_count(candidate_root)
    scanned = created = existing = historical_created = historical_existing = 0
    candidates: list[dict[str, Any]] = []
    for project in sorted(path for path in projects_root.iterdir() if path.is_dir() and not path.is_symlink()):
        conversations = project / "logs" / "conversations"
        if not conversations.is_dir() or conversations.is_symlink():
            continue
        for conversation in sorted(path for path in conversations.iterdir() if path.is_dir() and not path.is_symlink()):
            if scanned >= max_conversations:
                break
            scanned += 1
            candidate = _candidate(project.name, conversation)
            if candidate is None:
                continue
            historical_ir = build_historical_ir(candidate)
            historical_path = historical_ir_root / project.name / f"{historical_ir['historical_ir_id']}.json"
            if historical_path.is_file():
                current_ir = json.loads(historical_path.read_text(encoding="utf-8"))
                if current_ir != historical_ir:
                    raise ValueError("Historical IR id collision with different content")
                historical_existing += 1
            else:
                _write_json(historical_path, historical_ir)
                historical_created += 1
            output = candidate_root / project.name / f"{candidate['candidate_id']}.json"
            if output.is_file():
                current = json.loads(output.read_text(encoding="utf-8"))
                if current != candidate:
                    raise ValueError("candidate id collision with different content")
                existing += 1
            else:
                _write_json(output, candidate)
                created += 1
            candidates.append(candidate)
        if scanned >= max_conversations:
            break
    return {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "projects_root": str(projects_root),
        "candidate_root": str(candidate_root),
        "historical_ir_root": str(historical_ir_root),
        "scanned_conversations": scanned,
        "candidate_count": len(candidates),
        "before_candidate_count": before_candidate_count,
        "after_candidate_count": _candidate_count(candidate_root),
        "created_candidates": created,
        "existing_candidates": existing,
        "created_historical_irs": historical_created,
        "existing_historical_irs": historical_existing,
        "candidates": [{
            **{key: item[key] for key in ("candidate_id", "project_id", "conversation_id", "source_digest", "signals")},
            "historical_ir_id": build_historical_ir(item)["historical_ir_id"],
            "historical_ir_digest": historical_ir_digest(build_historical_ir(item)),
        } for item in candidates],
        "promotion_performed": False,
        "raw_conversation_copied": False,
        "credential_exposed": False,
    }
