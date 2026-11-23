#!/usr/bin/env python3
"""Read-only GitHub Issue / canonical WorkItem completion reconciliation.

Only an explicit issue state from a complete-enough caller-supplied snapshot
may be interpreted as closure. Missing issues are not treated as closed.
Never changes GitHub issues, grants authority or advances WorkItems.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCHEMA = "agentos.issue-completion-reconciliation/v1"
ID_RE = re.compile(r"gh-issue-([0-9]+)-(engineering|readonly|bounty-readonly)$")
ACTIVE = {"accepted", "in_progress", "waiting_external", "blocked", "verifying"}


def reconcile(issues: list[dict], state: dict) -> dict:
    if not isinstance(issues, list) or not isinstance(state, dict):
        raise ValueError("invalid_reconciliation_input")
    items = state.get("items")
    if not isinstance(items, dict):
        raise ValueError("work_items_required")
    by_number = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        number, status = issue.get("number"), issue.get("state")
        if type(number) is not int or number < 1 or status not in {"open", "closed"}:
            continue
        if number in by_number and by_number[number] != status:
            raise ValueError("conflicting_issue_states")
        by_number[number] = status

    findings = []
    for work_id, item in sorted(items.items()):
        match = ID_RE.fullmatch(work_id)
        if not match or not isinstance(item, dict):
            continue
        number = int(match.group(1))
        issue_state = by_number.get(number)
        if issue_state is None:
            continue  # May be a partial snapshot; never infer closure from absence.
        work_status = item.get("status")
        verification = item.get("verification")
        verified = (
            work_status == "done"
            and isinstance(verification, dict)
            and verification.get("status") == "passed"
            and isinstance(item.get("evidence"), list)
            and bool(item["evidence"])
        )
        if issue_state == "closed" and work_status in ACTIVE:
            code = "CLOSED_WITHOUT_VERIFIED_DONE"
        elif issue_state == "closed" and work_status == "done" and not verified:
            code = "CLOSED_WITHOUT_VERIFIED_DONE"
        elif issue_state == "closed" and work_status == "cancelled":
            code = "CLOSED_CANCELLED_REVIEW_REASON"
        elif issue_state == "closed" and work_status == "done" and verified:
            code = "VERIFIED_CLOSED"
        elif issue_state == "open" and work_status == "done" and verified:
            code = "VERIFIED_DONE_ISSUE_OPEN"
        else:
            code = "NO_CLOSURE_ANOMALY"
        findings.append({
            "issue_number": number,
            "work_id": work_id,
            "issue_state": issue_state,
            "work_status": work_status if isinstance(work_status, str) else "unknown",
            "verified_done": verified,
            "code": code,
        })
    problems = sum(row["code"] == "CLOSED_WITHOUT_VERIFIED_DONE" for row in findings)
    return {"schema": SCHEMA, "findings": findings, "closed_without_verified_done": problems,
            "changes_made": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issues-json", type=Path, required=True,
                        help="Explicit state-bearing GitHub Issues snapshot, open AND closed")
    parser.add_argument("--work-items-json", type=Path, required=True)
    args = parser.parse_args()
    issues = json.loads(args.issues_json.read_text(encoding="utf-8"))
    state = json.loads(args.work_items_json.read_text(encoding="utf-8"))
    result = reconcile(issues, state)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if result["closed_without_verified_done"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
