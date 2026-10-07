#!/usr/bin/env python3
"""Conservative PR backlog reconciliation.

Dry-run only. It never closes or merges pull requests.
Classifications are evidence-oriented:
- ACTIVE: recently updated.
- BLOCKED: GitHub reports merge conflicts/blocked state.
- ALREADY_LANDED: no commits ahead of main.
- NEEDS_REVIEW: stale/diverged/ambiguous and requires human or higher-level reconciliation.

Input is a JSON array or {"pull_requests": [...]} snapshot so the classifier is
fully testable and can be fed by any GitHub collector.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

SCHEMA = "agentos.pr-reconciliation/v1"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def age_days(updated_at: str, now: datetime) -> int:
    stamp = _parse_time(updated_at)
    return max(0, (now - stamp).days)


def classify(pr: dict[str, Any], *, now: datetime, stale_days: int = 7) -> dict[str, Any]:
    reasons: list[str] = []
    ahead = pr.get("ahead_by")
    behind = pr.get("behind_by")
    mergeable_state = str(pr.get("mergeable_state") or "")
    age = age_days(str(pr["updated_at"]), now)

    if ahead == 0:
        status = "ALREADY_LANDED"
        reasons.append("head_has_no_commits_ahead_of_main")
    elif mergeable_state in {"dirty", "blocked"}:
        status = "BLOCKED"
        reasons.append(f"mergeable_state={mergeable_state}")
    elif age <= stale_days:
        status = "ACTIVE"
        reasons.append(f"updated_within_{stale_days}_days")
    else:
        status = "NEEDS_REVIEW"
        reasons.append(f"stale_for_{age}_days")

    if isinstance(behind, int) and behind > 100:
        reasons.append(f"behind_main_by_{behind}_commits")
    if isinstance(ahead, int) and ahead > 100:
        reasons.append(f"ahead_of_main_by_{ahead}_commits")
    if isinstance(pr.get("files"), int) and pr["files"] > 50:
        reasons.append(f"large_diff_{pr['files']}_files")

    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "url": pr.get("url"),
        "status": status,
        "age_days": age,
        "ahead_by": ahead,
        "behind_by": behind,
        "mergeable_state": mergeable_state or None,
        "reasons": reasons,
    }


def reconcile(snapshot: Any, *, now: datetime, stale_days: int = 7) -> dict[str, Any]:
    prs = snapshot.get("pull_requests", []) if isinstance(snapshot, dict) else snapshot
    if not isinstance(prs, list):
        raise ValueError("snapshot_must_be_list_or_pull_requests_object")
    rows = [classify(pr, now=now, stale_days=stale_days) for pr in prs]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema": SCHEMA,
        "generated_at": now.isoformat(),
        "stale_days": stale_days,
        "counts": dict(sorted(counts.items())),
        "rows": rows,
        "dry_run": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--stale-days", type=int, default=7)
    ap.add_argument("--now", help="ISO timestamp for reproducible runs")
    args = ap.parse_args()

    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    report = reconcile(data, now=now, stale_days=max(1, args.stale_days))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
