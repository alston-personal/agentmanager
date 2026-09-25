#!/usr/bin/env python3
"""Durable AgentOS work-completion ledger.

A promised implementation may be handed off, blocked, resumed or verified, but
must never disappear merely because a chat, project or executor changed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

SCHEMA = "agentos.work-completion/v1"
ACTIVE = {"accepted", "in_progress", "blocked", "verifying"}
TERMINAL = {"done", "cancelled"}
ALLOWED = {
    "accepted": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "verifying", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "verifying": {"in_progress", "blocked", "done"},
    "done": set(),
    "cancelled": set(),
}
PRIORITY = {"in_progress": 0, "accepted": 1, "verifying": 2, "blocked": 3}
EXECUTION_OWNERS = {"role://completion.controller", "role://lobster"}
DEFAULT_LEASE_SECONDS = 1800


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lease_deadline(seconds: int = DEFAULT_LEASE_SECONDS) -> str:
    seconds = max(60, int(seconds))
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def lease_expired(item: dict[str, Any], at: datetime | None = None) -> bool:
    raw = str(item.get("lease_expires_at") or "")
    if not raw:
        return True
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    point = at or datetime.now(timezone.utc)
    return deadline <= point


def default_state() -> dict[str, Any]:
    return {"schema": SCHEMA, "generation": 0, "items": {}, "updated_at": now()}


def state_path() -> Path:
    root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    return root / "governance" / "work-items.json"


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA or not isinstance(payload.get("items"), dict):
        raise ValueError("work_completion_state_invalid")
    return payload


def save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema"] = SCHEMA
    state["generation"] = int(state.get("generation", 0)) + 1
    state["updated_at"] = now()
    fd, temp = tempfile.mkstemp(prefix=".work-items-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_item(item: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    wid = str(item.get("work_id") or "").strip()
    status = str(item.get("status") or "")
    if not wid:
        problems.append("work_id_missing")
    if status not in ACTIVE | TERMINAL:
        problems.append("status_invalid")
    if status in ACTIVE:
        if not str(item.get("owner") or "").strip():
            problems.append("active_owner_missing")
        if not str(item.get("next_action") or "").strip():
            problems.append("active_next_action_missing")
        if not str(item.get("lease_expires_at") or "").strip():
            problems.append("active_lease_missing")
        acceptance = item.get("acceptance")
        if not isinstance(acceptance, list) or not [x for x in acceptance if str(x).strip()]:
            problems.append("active_acceptance_missing")
    if status == "blocked" and not str(item.get("blocker") or "").strip():
        problems.append("blocked_reason_missing")
    if status == "done":
        evidence = item.get("evidence")
        verification = item.get("verification") or {}
        if not isinstance(evidence, list) or not evidence:
            problems.append("done_evidence_missing")
        if not isinstance(verification, dict) or verification.get("status") != "passed":
            problems.append("done_verification_missing")
    return problems


def register(
    path: Path,
    *,
    work_id: str,
    project_id: str,
    title: str,
    owner: str,
    next_action: str,
    acceptance: list[str],
    source: str = "",
    workspace: str = "",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    if not all(str(v).strip() for v in (work_id, project_id, title, owner, next_action)):
        raise ValueError("required_work_fields_missing")
    acceptance = [str(x).strip() for x in acceptance if str(x).strip()]
    if not acceptance:
        raise ValueError("acceptance_required")
    with locked(path):
        state = load(path)
        existing = state["items"].get(work_id)
        if existing and existing.get("status") not in TERMINAL:
            return existing
        if existing and existing.get("status") in TERMINAL:
            raise ValueError("terminal_work_id_cannot_be_reused")
        stamp = now()
        item = {
            "work_id": work_id,
            "project_id": project_id,
            "title": title,
            "status": "accepted",
            "owner": owner,
            "owner_generation": 1,
            "lease_expires_at": lease_deadline(lease_seconds),
            "next_action": next_action,
            "acceptance": acceptance,
            "source": source or None,
            "workspace": workspace or None,
            "blocker": None,
            "evidence": [],
            "verification": None,
            "created_at": stamp,
            "updated_at": stamp,
            "history": [{"at": stamp, "event": "registered", "actor": owner}],
        }
        problems = validate_item(item)
        if problems:
            raise ValueError(",".join(problems))
        state["items"][work_id] = item
        save(path, state)
        return item


def transition(
    path: Path,
    *,
    work_id: str,
    target: str,
    actor: str,
    next_action: str | None = None,
    blocker: str | None = None,
    evidence: list[str] | None = None,
    verification: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    with locked(path):
        state = load(path)
        item = state["items"].get(work_id)
        if not item:
            raise KeyError("work_item_not_found")
        current = str(item["status"])
        if target == current:
            return item
        if target not in ALLOWED.get(current, set()):
            raise ValueError(f"invalid_transition:{current}->{target}")
        if next_action is not None:
            item["next_action"] = next_action.strip()
        if target in ACTIVE and not str(item.get("next_action") or "").strip():
            raise ValueError("active_next_action_required")
        item["status"] = target
        item["updated_at"] = now()
        if target in ACTIVE:
            item["lease_expires_at"] = lease_deadline(lease_seconds)
        else:
            item["lease_expires_at"] = None
        if target == "blocked":
            if not blocker or not blocker.strip():
                raise ValueError("blocked_reason_required")
            item["blocker"] = blocker.strip()
        else:
            item["blocker"] = None
        if evidence:
            item.setdefault("evidence", []).extend(str(x).strip() for x in evidence if str(x).strip())
        if target == "done":
            if not evidence and not item.get("evidence"):
                raise ValueError("done_evidence_required")
            if verification != "passed":
                raise ValueError("done_verification_required")
            item["verification"] = {"status": "passed", "verified_by": actor, "at": now()}
            item["next_action"] = ""
        item.setdefault("history", []).append(
            {"at": now(), "event": "transition", "from": current, "to": target, "actor": actor}
        )
        problems = validate_item(item)
        if problems:
            raise ValueError(",".join(problems))
        save(path, state)
        return item


def handoff(
    path: Path, *, work_id: str, actor: str, new_owner: str, next_action: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    if not new_owner.strip() or not next_action.strip():
        raise ValueError("handoff_owner_and_next_action_required")
    with locked(path):
        state = load(path)
        item = state["items"].get(work_id)
        if not item:
            raise KeyError("work_item_not_found")
        if item.get("status") in TERMINAL:
            raise ValueError("terminal_work_cannot_be_handed_off")
        previous = item.get("owner")
        item["owner"] = new_owner.strip()
        item["owner_generation"] = int(item.get("owner_generation") or 0) + 1
        item["lease_expires_at"] = lease_deadline(lease_seconds)
        item["next_action"] = next_action.strip()
        item["updated_at"] = now()
        item.setdefault("history", []).append(
            {
                "at": now(),
                "event": "handoff",
                "actor": actor,
                "from_owner": previous,
                "to_owner": item["owner"],
                "owner_generation": item["owner_generation"],
            }
        )
        problems = validate_item(item)
        if problems:
            raise ValueError(",".join(problems))
        save(path, state)
        return item


def heartbeat(
    path: Path, *, work_id: str, actor: str, lease_seconds: int = DEFAULT_LEASE_SECONDS
) -> dict[str, Any]:
    with locked(path):
        state = load(path)
        item = state["items"].get(work_id)
        if not item:
            raise KeyError("work_item_not_found")
        if item.get("status") not in ACTIVE:
            raise ValueError("terminal_work_has_no_lease")
        if str(item.get("owner")) != actor:
            raise ValueError("heartbeat_owner_mismatch")
        item["lease_expires_at"] = lease_deadline(lease_seconds)
        item["updated_at"] = now()
        item.setdefault("history", []).append(
            {"at": now(), "event": "heartbeat", "actor": actor, "owner_generation": item.get("owner_generation")}
        )
        save(path, state)
        return item


def reclaim_stale(
    path: Path, *, actor: str = "role://completion.watchdog",
    new_owner: str = "role://completion.controller",
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> list[str]:
    reclaimed: list[str] = []
    with locked(path):
        state = load(path)
        for work_id, item in sorted(state["items"].items()):
            if item.get("status") not in ACTIVE or not lease_expired(item):
                continue
            previous = str(item.get("owner") or "")
            if previous in EXECUTION_OWNERS:
                item["lease_expires_at"] = lease_deadline(lease_seconds)
                item["updated_at"] = now()
                continue
            item["owner"] = new_owner
            item["owner_generation"] = int(item.get("owner_generation") or 0) + 1
            item["lease_expires_at"] = lease_deadline(lease_seconds)
            item["updated_at"] = now()
            item.setdefault("history", []).append(
                {
                    "at": now(),
                    "event": "stale_reclaim",
                    "actor": actor,
                    "from_owner": previous,
                    "to_owner": new_owner,
                    "owner_generation": item["owner_generation"],
                }
            )
            reclaimed.append(work_id)
        if reclaimed:
            save(path, state)
    return reclaimed


def next_item(path: Path, *, include_blocked: bool = False) -> dict[str, Any] | None:
    state = load(path)
    candidates = []
    for item in state["items"].values():
        status = item.get("status")
        if status not in ACTIVE:
            continue
        if status == "blocked" and not include_blocked:
            continue
        candidates.append(item)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (PRIORITY.get(str(x.get("status")), 9), x.get("updated_at", ""), x["work_id"]))
    return candidates[0]


def audit(path: Path) -> tuple[list[str], list[str]]:
    state = load(path)
    errors: list[str] = []
    active: list[str] = []
    for work_id, item in sorted(state["items"].items()):
        for problem in validate_item(item):
            errors.append(f"{work_id}:{problem}")
        if item.get("status") in ACTIVE:
            active.append(work_id)
    return errors, active


def board_projection(path: Path) -> str:
    state = load(path)
    active = [
        item for item in state["items"].values()
        if item.get("status") in ACTIVE and str(item.get("owner") or "") in EXECUTION_OWNERS
    ]
    if not active:
        return ""
    marks = {"accepted": " ", "in_progress": "/", "blocked": "!", "verifying": "/"}
    projects: dict[str, list[dict[str, Any]]] = {}
    for item in active:
        projects.setdefault(str(item["project_id"]), []).append(item)
    lines = [
        "<!-- WORK_COMPLETION_START -->",
        "## 🧭 Completion Controller — 必須完成／交棒，不得遺失",
        "",
    ]
    for project in sorted(projects):
        lines.append(f"### 📦 {project}")
        for item in sorted(projects[project], key=lambda x: (PRIORITY.get(x["status"], 9), x["work_id"])):
            mark = marks[item["status"]]
            action = str(item["next_action"]).replace("\n", " ").strip()
            lines.append(f"- [{mark}] [WI:{item['work_id']}] {action}")
        lines.append("")
    lines.append("<!-- WORK_COMPLETION_END -->")
    return "\n".join(lines).rstrip() + "\n"


def project_board(path: Path, board: Path) -> None:
    managed = board_projection(path)
    current = board.read_text(encoding="utf-8") if board.exists() else "# AgentOS Task Board\n"
    start = "<!-- WORK_COMPLETION_START -->"
    end = "<!-- WORK_COMPLETION_END -->"
    if start in current and end in current:
        before, tail = current.split(start, 1)
        _, after = tail.split(end, 1)
        current = before.rstrip() + "\n\n" + after.lstrip()
    if managed:
        lines = current.splitlines()
        insert_at = 1 if lines and lines[0].startswith("#") else 0
        new_lines = lines[:insert_at] + ["", managed.rstrip(), ""] + lines[insert_at:]
        current = "\n".join(new_lines).rstrip() + "\n"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_text(current, encoding="utf-8")


def item_id_from_task(text: str) -> str | None:
    import re
    match = re.search(r"\[WI:([A-Za-z0-9._:-]+)\]", text)
    return match.group(1) if match else None


def verified_done(path: Path, *, work_id: str, actor: str, evidence: str) -> dict[str, Any]:
    item = load(path)["items"].get(work_id)
    if not item:
        raise KeyError("work_item_not_found")
    status = item["status"]
    if status == "accepted":
        transition(path, work_id=work_id, target="in_progress", actor=actor, next_action=item["next_action"])
        status = "in_progress"
    if status == "blocked":
        transition(path, work_id=work_id, target="in_progress", actor=actor, next_action=item["next_action"])
        status = "in_progress"
    if status == "in_progress":
        transition(path, work_id=work_id, target="verifying", actor=actor, next_action="record verified completion receipt")
    return transition(
        path,
        work_id=work_id,
        target="done",
        actor=actor,
        evidence=[evidence],
        verification="passed",
    )


def cli() -> int:
    parser = argparse.ArgumentParser(description="AgentOS durable work-completion controller")
    parser.add_argument("--state", type=Path, default=state_path())
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register")
    p.add_argument("--id", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--next-action", required=True)
    p.add_argument("--accept", action="append", required=True)
    p.add_argument("--source", default="")
    p.add_argument("--workspace", default="")
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("transition")
    p.add_argument("--id", required=True)
    p.add_argument("--to", required=True, choices=sorted(ACTIVE | TERMINAL))
    p.add_argument("--actor", required=True)
    p.add_argument("--next-action")
    p.add_argument("--blocker")
    p.add_argument("--evidence", action="append")
    p.add_argument("--verification", choices=["passed"])
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("handoff")
    p.add_argument("--id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--new-owner", required=True)
    p.add_argument("--next-action", required=True)
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("heartbeat")
    p.add_argument("--id", required=True)
    p.add_argument("--actor", required=True)
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("reclaim-stale")
    p.add_argument("--actor", default="role://completion.watchdog")
    p.add_argument("--new-owner", default="role://completion.controller")
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)

    p = sub.add_parser("next")
    p.add_argument("--include-blocked", action="store_true")

    p = sub.add_parser("audit")

    p = sub.add_parser("project-board")
    p.add_argument("--board", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "register":
        result = register(
            args.state, work_id=args.id, project_id=args.project, title=args.title,
            owner=args.owner, next_action=args.next_action, acceptance=args.accept,
            source=args.source, workspace=args.workspace, lease_seconds=args.lease_seconds,
        )
    elif args.command == "transition":
        result = transition(
            args.state, work_id=args.id, target=args.to, actor=args.actor,
            next_action=args.next_action, blocker=args.blocker,
            evidence=args.evidence, verification=args.verification,
            lease_seconds=args.lease_seconds,
        )
    elif args.command == "handoff":
        result = handoff(
            args.state, work_id=args.id, actor=args.actor,
            new_owner=args.new_owner, next_action=args.next_action,
            lease_seconds=args.lease_seconds,
        )
    elif args.command == "heartbeat":
        result = heartbeat(
            args.state, work_id=args.id, actor=args.actor, lease_seconds=args.lease_seconds,
        )
    elif args.command == "reclaim-stale":
        reclaimed = reclaim_stale(
            args.state, actor=args.actor, new_owner=args.new_owner,
            lease_seconds=args.lease_seconds,
        )
        result = {"reclaimed": reclaimed}
    elif args.command == "next":
        result = next_item(args.state, include_blocked=args.include_blocked)
    elif args.command == "audit":
        errors, active = audit(args.state)
        print(json.dumps({"schema": SCHEMA, "errors": errors, "active": active}, ensure_ascii=False, indent=2))
        return 2 if errors else 0
    elif args.command == "project-board":
        project_board(args.state, args.board)
        result = {"projected": True, "board": str(args.board)}
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
