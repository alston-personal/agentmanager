#!/usr/bin/env python3
"""Fail-closed GitHub Issue -> AgentOS WorkItem intake.

This module takes an already-fetched GitHub API issue list; it does not fetch,
change labels, run executors or publish anything. Only explicit opt-in tasks
with an executable acceptance contract are eligible.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from work_completion import register, load, TERMINAL

REQUIRED_LABELS = {"agentos:approved", "agentos:lobster"}
SAFE_LABEL = "agentos:readonly"
DISALLOWED = {"blocked", "needs-decision", "needs-approval", "security", "production-change"}
ALLOWLIST = re.compile(r"^檢查連接埠\s+(\d{1,5})$")
URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)$")


def eligible(issue: dict, repo: str) -> tuple[bool, str]:
    if not isinstance(issue, dict) or issue.get("pull_request"):
        return False, "not_issue"
    if issue.get("state") != "open":
        return False, "not_open"
    labels = {str(x.get("name", "")).lower() for x in issue.get("labels", []) if isinstance(x, dict)}
    if not REQUIRED_LABELS.issubset(labels) or SAFE_LABEL not in labels:
        return False, "not_approved_readonly"
    if labels & DISALLOWED:
        return False, "blocked_label"
    if not isinstance(issue.get("body"), str):
        return False, "no_body"
    match = re.search(r"(?m)^Action:\s*(.+?)\s*$", issue["body"])
    accept = re.search(r"(?m)^Acceptance:\s*(.+?)\s*$", issue["body"])
    if not match or not accept:
        return False, "contract_missing"
    action = match.group(1).strip()
    port = ALLOWLIST.fullmatch(action)
    if not port or not (1 <= int(port.group(1)) <= 65535):
        return False, "unsupported_action"
    if not accept.group(1).strip():
        return False, "acceptance_empty"
    u = URL.fullmatch(str(issue.get("html_url", "")))
    if not u or f"{u.group(1)}/{u.group(2)}".lower() != repo.lower() or int(u.group(3)) != issue.get("number"):
        return False, "source_mismatch"
    return True, "eligible"


def intake(issues: list[dict], *, repo: str, state: Path, workspace: Path) -> list[dict]:
    result = []
    for issue in issues:
        ok, why = eligible(issue, repo)
        if not ok:
            result.append({"number": issue.get("number"), "status": "skipped", "reason": why})
            continue
        body = issue["body"]
        action = re.search(r"(?m)^Action:\s*(.+?)\s*$", body).group(1).strip()
        acceptance = re.search(r"(?m)^Acceptance:\s*(.+?)\s*$", body).group(1).strip()
        number = int(issue["number"])
        work_id = f"gh-issue-{number}-readonly"
        previous = load(state)["items"].get(work_id)
        if previous and previous.get("status") in TERMINAL:
            result.append({"number": number, "status": "already_terminal", "work_id": work_id})
            continue
        item = register(
            state, work_id=work_id, project_id="agentos-core",
            title=str(issue.get("title") or work_id)[:160],
            owner="role://lobster", source=issue["html_url"],
            workspace=str(workspace), next_action=action, acceptance=[acceptance]
        )
        result.append({"number": number, "status": item["status"], "work_id": work_id})
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--issues-json", type=Path, required=True)
    p.add_argument("--repo", default="alston-personal/agentmanager")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    a = p.parse_args()
    issues = json.loads(a.issues_json.read_text(encoding="utf-8"))
    if not isinstance(issues, list): raise ValueError("issue_list_required")
    print(json.dumps(intake(issues, repo=a.repo, state=a.state, workspace=a.workspace)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
