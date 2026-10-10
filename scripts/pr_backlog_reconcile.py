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
import re
from pathlib import Path
from typing import Any

SCHEMA = "agentos.pr-reconciliation/v2"


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


def explicit_supersessions(prs: list[dict[str, Any]]) -> dict[int, int]:
    """Return old_pr -> newer_pr only for explicit rebased-successor evidence."""
    open_numbers = {int(pr.get("number")) for pr in prs if pr.get("number") is not None}
    result: dict[int, int] = {}
    for pr in prs:
        body = str(pr.get("body") or "")
        newer = int(pr.get("number"))
        for match in re.finditer(r"(?i)rebased\s+follow-up\s+to\s+#(\d+)", body):
            older = int(match.group(1))
            if older in open_numbers and older != newer:
                result[older] = newer
    return result


def _strip_version_suffix(value: str) -> str:
    """Normalize an explicit trailing vN version marker, nothing broader."""
    return re.sub(r"(?i)(?:[\s_-]+v\d+)$", "", value.strip())


def merged_supersessions(
    open_prs: list[dict[str, Any]],
    merged_prs: list[dict[str, Any]],
) -> dict[int, int]:
    """Return old open PR -> merged successor using deliberately narrow evidence.

    A merged PR is considered a successor only when all of these hold:
    - successor number is newer;
    - base branch is identical;
    - title differs only by an explicit trailing vN marker;
    - head branch differs only by an explicit trailing -vN/_vN marker.

    This intentionally prefers false negatives over false positives.
    """
    result: dict[int, int] = {}
    for old in open_prs:
        old_number = int(old.get("number"))
        old_title = str(old.get("title") or "")
        old_head = str(old.get("head") or "")
        old_base = str(old.get("base") or "")
        if not old_title or not old_head or not old_base:
            continue
        for newer in merged_prs:
            newer_number = int(newer.get("number"))
            if newer_number <= old_number:
                continue
            if str(newer.get("base") or "") != old_base:
                continue
            newer_title = str(newer.get("title") or "")
            newer_head = str(newer.get("head") or "")
            if _strip_version_suffix(newer_title) != _strip_version_suffix(old_title):
                continue
            if _strip_version_suffix(newer_head) != _strip_version_suffix(old_head):
                continue
            result[old_number] = newer_number
            break
    return result


def reconcile(snapshot: Any, *, now: datetime, stale_days: int = 7) -> dict[str, Any]:
    prs = snapshot.get("pull_requests", []) if isinstance(snapshot, dict) else snapshot
    merged_prs = snapshot.get("merged_pull_requests", []) if isinstance(snapshot, dict) else []
    if not isinstance(prs, list):
        raise ValueError("snapshot_must_be_list_or_pull_requests_object")
    if not isinstance(merged_prs, list):
        raise ValueError("merged_pull_requests_must_be_list")
    explicit = explicit_supersessions(prs)
    merged = merged_supersessions(prs, merged_prs)
    rows = [classify(pr, now=now, stale_days=stale_days) for pr in prs]
    for row in rows:
        number = int(row["number"])
        if number in explicit:
            row["status"] = "SUPERSEDED"
            row["superseded_by"] = explicit[number]
            row["reasons"].insert(0, f"explicit_rebased_follow_up=#{explicit[number]}")
        elif number in merged:
            row["status"] = "SUPERSEDED"
            row["superseded_by"] = merged[number]
            row["reasons"].insert(0, f"merged_versioned_successor=#{merged[number]}")
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
