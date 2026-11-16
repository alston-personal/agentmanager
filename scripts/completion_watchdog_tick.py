"""Single bounded Completion Ledger wake tick through existing Chronos.

This runs the existing verified due-time transition, then (only for the exact
already-approved WoW #2134 WorkItem) projects an inspect-only Paw assignment.
Neither step grants execution, delivery, model, merge or deployment authority.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from work_completion import load, wake_due
from approved_wow_paw_handoff import WORK_ID, handoff


_PROJECT_RE = re.compile(r"\[([a-zA-Z0-9_.-]+)\]")
_AC_MARKERS = ("[AC:", "[驗收:", "驗收標準", "acceptance")


def _extract_project(item: str) -> str:
    match = _PROJECT_RE.search(item)
    return match.group(1) if match else "unknown"


def consume_atlas_attention_queue(root: Path, items: dict) -> dict:
    """Consume atlas/attention_queue.json so open loops never remain unowned orphans."""
    atlas_dir = root / "atlas"
    attention_path = atlas_dir / "attention_queue.json"
    if not attention_path.is_file():
        return {"status": "no_attention_queue", "orphan_count": 0, "needs_human_triage_count": 0, "ready_for_intake_count": 0}

    try:
        attention = json.loads(attention_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid_attention_queue", "orphan_count": 0, "needs_human_triage_count": 0, "ready_for_intake_count": 0}

    top_items = attention.get("top_attention_items") or []
    if not isinstance(top_items, list):
        top_items = []

    triage_path = atlas_dir / "triage_queue.json"
    existing_triage: dict[str, dict] = {}
    if triage_path.is_file():
        try:
            loaded = json.loads(triage_path.read_text(encoding="utf-8"))
            for entry in loaded.get("items") or []:
                if isinstance(entry, dict) and entry.get("triage_id"):
                    existing_triage[str(entry["triage_id"])] = entry
        except (OSError, json.JSONDecodeError):
            existing_triage = {}

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tracked_titles = {str(v.get("title") or "").strip() for v in items.values() if isinstance(v, dict)}
    triaged_items: list[dict] = []
    needs_human = 0
    ready_intake = 0

    for raw in top_items:
        text = str(raw or "").strip()
        if not text:
            continue
        triage_id = "atlas-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        project_id = _extract_project(text)
        if triage_id in items or text in tracked_titles:
            status = "IN_COMPLETION_LEDGER"
            reason = "already tracked in work-items.json"
        elif any(marker in text for marker in _AC_MARKERS) and project_id != "unknown":
            status = "READY_FOR_INTAKE"
            reason = "has explicit acceptance marker; awaiting authorized intake"
            ready_intake += 1
        else:
            status = "BLOCKED_NEEDS_HUMAN_TRIAGE"
            reason = "missing explicit acceptance criteria or project intake authorization"
            needs_human += 1

        prev = existing_triage.get(triage_id) or {}
        triaged_items.append({
            "triage_id": triage_id,
            "project_id": project_id,
            "title": text[:240],
            "status": status,
            "reason": reason,
            "first_seen_at": prev.get("first_seen_at") or now_iso,
            "updated_at": now_iso,
        })

    triage_payload = {
        "schema": "agentos.atlas-triage/v1",
        "cycle": attention.get("cycle"),
        "open_loop_count": attention.get("open_loop_count", len(triaged_items)),
        "orphan_count": 0,
        "needs_human_triage_count": needs_human,
        "ready_for_intake_count": ready_intake,
        "updated_at": now_iso,
        "items": triaged_items,
    }
    tmp = triage_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(triage_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(triage_path)
    return {
        "status": "triaged",
        "cycle": attention.get("cycle"),
        "orphan_count": 0,
        "needs_human_triage_count": needs_human,
        "ready_for_intake_count": ready_intake,
    }


def tick(data_root: Path, *, at: datetime | None = None) -> dict:
    root = data_root.expanduser().resolve()
    state = root / "governance" / "work-items.json"
    if not state.is_file():
        raise FileNotFoundError("completion_ledger_missing")
    lock_path = root / "governance" / "completion-watchdog-tick.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"schema": "agentos.completion-watchdog-tick/v1",
                    "status": "already_running", "credential_exposed": False}
        awakened = wake_due(state, actor="role://completion.watchdog", at=at)
        items = load(state).get("items") or {}
        if WORK_ID not in items:
            result = {"status": "no_approved_wow_work"}
        else:
            # Handoff itself checks the exact source, role, scope and authority.
            result = handoff(completion_state=state,
                             runtime_root=root / "employee-runtime")
        atlas_triage = consume_atlas_attention_queue(root, items)
        return {
            "schema": "agentos.completion-watchdog-tick/v1",
            "status": "completed",
            "awakened_wow": WORK_ID in awakened,
            "paw_projection": result.get("status", "not_registered"),
            "paw_registered": result.get("assignment_registered") is True,
            "atlas_triage": atlas_triage,
            "credential_exposed": False,
        }


def main() -> int:
    root = Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")
    if not root.is_absolute():
        raise SystemExit("agent_data_root_must_be_absolute")
    print(json.dumps(tick(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
