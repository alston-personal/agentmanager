#!/usr/bin/env python3
from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DATA_REPO = Path("/home/ubuntu/agent-data")
DATA_HTTPS = "https://github.com/alston-personal/my-agent-data.git"
GIT_CREDENTIAL = "credential.helper=!gh auth git-credential"
PERSONA = Path("personas/sunlake-milkcat")
IR_REL = PERSONA / "ir/current.json"
IR_HISTORY_DIR = PERSONA / "ir/history"
EVENTS_REL = PERSONA / "events/events.jsonl"
GROWTH_DIR = PERSONA / "growth_events"

ADOPTED_STATUSES = {"adopted", "adopted_as_interaction_policy", "promoted", "validated_and_promoted"}


def run(args: list[str], *, cwd: Path = DATA_REPO, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, timeout=60, check=False)
    if check and result.returncode:
        raise RuntimeError("git_operation_failed")
    return result


def show_text(ref: str, rel: Path) -> str:
    return run(["git", "show", f"{ref}:{rel.as_posix()}"]).stdout


def parse_events(raw: str) -> list[dict]:
    rows: list[dict] = []
    for line in raw.splitlines():
        try:
            item = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def event_id(row: dict) -> str:
    return str(row.get("event_id") or row.get("object_id") or "").strip()


def safe_growth_delta(doc: dict, rel: str) -> dict:
    change = doc.get("change") if isinstance(doc.get("change"), dict) else {}
    delta = str(change.get("after") or doc.get("hypothesis") or doc.get("observation") or "").strip()
    return {
        "growth_ref": "../growth_events/" + Path(rel).name,
        "status": str(doc.get("status") or ""),
        "delta": delta[:700],
    }


def main() -> int:
    if os.getuid() != 1001 or os.environ.get("USER") not in (None, "", "ubuntu"):
        print("mio_persona_ir_evolve=WRONG_USER")
        return 2
    if not (DATA_REPO / ".git").exists():
        print("mio_persona_ir_evolve=DATA_REPO_MISSING")
        return 3

    remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    safe = remote.rstrip("/").removesuffix(".git")
    if not safe.endswith("/my-agent-data") and not safe.endswith(":alston-personal/my-agent-data"):
        print("mio_persona_ir_evolve=UNEXPECTED_REMOTE")
        return 4

    # Serialize git metadata access with the persona event synchronizer. The
    # persistent monitor and deployment acceptance may run close together.
    lock_path = Path("/tmp/agentos-mio-persona-data-git.lock")
    lock = lock_path.open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    fetched = False
    for _ in range(3):
        result = run(["git", "-c", GIT_CREDENTIAL, "fetch", DATA_HTTPS, "+refs/heads/main:refs/remotes/origin/main"], check=False)
        if result.returncode == 0:
            fetched = True
            break
        time.sleep(1)
    if not fetched:
        err = str(result.stderr or "").lower()
        if "cannot lock" in err or "fetch_head.lock" in err or "index.lock" in err:
            category = "LOCK"
        elif "could not resolve host" in err or "temporary failure in name resolution" in err:
            category = "DNS"
        elif "authentication failed" in err or "could not read username" in err or "permission denied" in err:
            category = "AUTH_OR_PERMISSION"
        elif "dubious ownership" in err:
            category = "OWNERSHIP"
        elif "unable to access" in err or "failed to connect" in err or "connection timed out" in err:
            category = "NETWORK"
        else:
            category = "OTHER"
        print("mio_persona_ir_evolve=GIT_FETCH_FAILED_" + category)
        return 8
    ref = "origin/main"

    try:
        current = json.loads(show_text(ref, IR_REL))
        events = parse_events(show_text(ref, EVENTS_REL))
    except (RuntimeError, ValueError, TypeError):
        print("mio_persona_ir_evolve=CANONICAL_INPUT_UNAVAILABLE")
        return 5
    if current.get("schema") != "agentos.persona-ir/v1":
        print("mio_persona_ir_evolve=IR_SCHEMA_MISMATCH")
        return 6

    # Collect only explicit, evidence-backed promotions. Raw experiences advance
    # the journey/cursor but do not silently rewrite stable beliefs.
    growth_paths = [
        p for p in run(["git", "ls-tree", "-r", "--name-only", ref, GROWTH_DIR.as_posix()]).stdout.splitlines()
        if p.endswith(".json")
    ]
    promoted: list[dict] = []
    for rel in growth_paths:
        try:
            doc = json.loads(show_text(ref, Path(rel)))
        except (RuntimeError, ValueError, TypeError):
            continue
        if str(doc.get("status") or "") in ADOPTED_STATUSES:
            promoted.append(safe_growth_delta(doc, rel))
    promoted.sort(key=lambda x: x["growth_ref"])

    journey = current.get("journey") if isinstance(current.get("journey"), dict) else {}
    processed = {str(x) for x in (journey.get("processed_event_ids") or []) if str(x)}
    all_ids = [event_id(row) for row in events if event_id(row)]
    new_rows = [row for row in events if event_id(row) and event_id(row) not in processed]

    old_growth = {
        str(x.get("growth_ref") or ""): x
        for x in (current.get("promoted_growth") or [])
        if isinstance(x, dict) and str(x.get("growth_ref") or "")
    }
    new_growth = [x for x in promoted if x["growth_ref"] not in old_growth]

    if not new_rows and not new_growth:
        print("mio_persona_ir_evolve=NO_CHANGE")
        print("mio_persona_ir_revision=" + str(current.get("revision") or 0))
        return 0

    nxt = copy.deepcopy(current)
    parent_ir = str(current.get("ir_id") or "")
    revision = int(current.get("revision") or 0) + 1
    now = datetime.now(timezone.utc).replace(microsecond=0)
    nxt["parent_ir_id"] = parent_ir or None
    nxt["revision"] = revision
    nxt["ir_id"] = f"mio-ir-{now.strftime('%Y%m%d')}-r{revision}"
    nxt["generated_at"] = now.isoformat().replace("+00:00", "Z")

    j = nxt.setdefault("journey", {})
    j["processed_event_ids"] = all_ids
    j["total_events_seeded"] = len(all_ids)
    counters = Counter(str(row.get("type") or "unknown") for row in events)
    j["event_type_counts"] = dict(sorted(counters.items()))
    recent = list(j.get("recent_experience_refs") or [])
    for row in new_rows:
        recent.append({
            "event_ref": event_id(row),
            "type": str(row.get("type") or "unknown"),
            "timestamp": row.get("timestamp") or row.get("observed_at"),
            "summary": str(row.get("summary") or row.get("interaction_summary") or row.get("text") or "")[:240],
        })
    j["recent_experience_refs"] = recent[-24:]
    if all_ids:
        j["last_event_ref"] = all_ids[-1]

    merged = list(nxt.get("promoted_growth") or [])
    merged.extend(new_growth)
    nxt["promoted_growth"] = merged
    metrics = nxt.setdefault("metrics", {})
    metrics["validated_growth_units"] = len(promoted)
    metrics["last_ir_advance_new_events"] = len(new_rows)
    metrics["last_ir_advance_new_growth_promotions"] = len(new_growth)

    # Make the causal distinction explicit in each revision.
    evolution = nxt.setdefault("evolution", {})
    evolution["last_advance_reason"] = {
        "new_event_refs": [event_id(row) for row in new_rows],
        "new_growth_refs": [x["growth_ref"] for x in new_growth],
        "rule": "raw events update lived history; durable belief/behavior deltas require explicit promoted growth evidence",
    }

    root = Path(tempfile.mkdtemp(prefix="mio-persona-ir-"))
    work = root / "work"
    try:
        run(["git", "worktree", "add", "--detach", str(work), ref])
        out = work / IR_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        history = work / IR_HISTORY_DIR / (str(nxt["ir_id"]) + ".json")
        history.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(nxt, ensure_ascii=False, indent=2) + "\n"
        out.write_text(encoded, encoding="utf-8")
        history.write_text(encoded, encoding="utf-8")
        run(["git", "add", IR_REL.as_posix(), history.relative_to(work).as_posix()], cwd=work)
        run([
            "git", "-c", "user.name=AgentOS Persona Growth",
            "-c", "user.email=agentos-persona-growth@users.noreply.github.com",
            "commit", "-m", f"chore(mio): advance persona IR to r{revision}",
        ], cwd=work)
        pushed = run(["git", "-c", GIT_CREDENTIAL, "push", DATA_HTTPS, "HEAD:main"], cwd=work, check=False)
        if pushed.returncode:
            print("mio_persona_ir_evolve=PUSH_FAILED")
            return 7
        # The push succeeded. Refresh the remote-tracking ref without another
        # network fetch so the following reply decision loads this exact IR.
        head = run(["git", "rev-parse", "HEAD"], cwd=work).stdout.strip()
        if re.fullmatch(r"[0-9a-f]{40}", head):
            run(["git", "update-ref", "refs/remotes/origin/main", head], cwd=DATA_REPO)
        print("mio_persona_ir_evolve=PASS")
        print("mio_persona_ir_revision=" + str(revision))
        print("mio_persona_ir_new_events=" + str(len(new_rows)))
        print("mio_persona_ir_new_growth=" + str(len(new_growth)))
        return 0
    finally:
        try:
            run(["git", "worktree", "remove", "--force", str(work)], check=False)
        except Exception:
            pass
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
