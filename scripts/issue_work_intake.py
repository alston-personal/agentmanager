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
from work_completion import register, register_intake_envelope, load, TERMINAL, INTAKE_SCHEMA

REQUIRED_LABELS = {"agentos:approved", "agentos:lobster"}
ENGINEERING_LABELS = {"agentos:approved", "agentos:engineering"}
PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_LABEL = "agentos:readonly"
DISALLOWED = {"blocked", "needs-decision", "needs-approval", "security", "production-change"}
ALLOWLIST = re.compile(r"^檢查連接埠\s+(\d{1,5})$")
BOUNTY_ACTION = "盤點公開懸賞候選案"
BOUNTY_LABEL = "agentos:bounty-readonly"
URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)$")


def eligible(issue: dict, repo: str) -> tuple[bool, str]:
    if not isinstance(issue, dict) or "pull_request" in issue:
        return False, "not_issue"
    if issue.get("state") != "open":
        return False, "not_open"
    labels = {str(x.get("name", "")).lower() for x in issue.get("labels", []) if isinstance(x, dict)}
    engineering = ENGINEERING_LABELS.issubset(labels)
    readonly = REQUIRED_LABELS.issubset(labels) and SAFE_LABEL in labels
    if not (readonly or engineering) or (engineering and readonly):
        return False, "not_explicitly_approved_or_ambiguous"
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
    bounded_port = bool(port and 1 <= int(port.group(1)) <= 65535)
    bounded_bounty = action == BOUNTY_ACTION and BOUNTY_LABEL in labels
    if engineering:
        project = re.search(r"(?m)^Project:\s*(\S+)\s*$", issue["body"])
        if not project or not PROJECT_ID.fullmatch(project.group(1)):
            return False, "engineering_project_required"
        if not 12 <= len(action) <= 500:
            return False, "engineering_action_size_invalid"
        # Intake is durable *data*, never a parsed command or authority grant.
        if any(re.search(pattern, action, re.IGNORECASE) for pattern in (
            r"(^|\s)(?:sudo|rm\s+-|curl\s+|wget\s+|powershell(?:\.exe)?\s+|bash\s+-c|cmd(?:\.exe)?\s+/c)",
            r"(?:\$\(|`|&&|\|\||\s>\s|\s\|\s)",
        )):
            return False, "engineering_shell_like_action"
    elif not (bounded_port or bounded_bounty):
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
        labels = {str(x.get("name", "")).lower() for x in issue.get("labels", []) if isinstance(x, dict)}
        engineering = ENGINEERING_LABELS.issubset(labels)
        is_bounty = not engineering and action == BOUNTY_ACTION
        work_id = (f"gh-issue-{number}-engineering" if engineering else
                   f"gh-issue-{number}-bounty-readonly" if is_bounty else
                   f"gh-issue-{number}-readonly")
        previous = load(state)["items"].get(work_id)
        if previous and previous.get("status") in TERMINAL:
            result.append({"number": number, "status": "already_terminal", "work_id": work_id})
            continue
        if engineering:
            project = re.search(r"(?m)^Project:\s*(\S+)\s*$", body).group(1)
            # No caller-controlled executable, working directory, owner or capability.
            item = register_intake_envelope(state, {
                "schema": INTAKE_SCHEMA, "work_id": work_id,
                "project_id": project, "title": str(issue.get("title") or work_id)[:160],
                "next_action": action, "acceptance": [acceptance],
                "source": issue["html_url"], "intake_kind": "engineering",
            })
            result.append({"number": number, "status": item["status"], "work_id": work_id,
                           "intake_kind": "engineering", "execution_authorized": False})
            continue
        item = register(
            state, work_id=work_id, project_id="agentos-core",
            title=str(issue.get("title") or work_id)[:160],
            owner="role://lobster", source=issue["html_url"],
            workspace=str(workspace), next_action=(
                "唯讀盤點公開 GitHub 懸賞候選案；查核 Issue 開啟狀態、獎金可信度與重複 PR；"
                "僅回報來源與判斷證據，不得寫入外部倉庫、留言、領取或承諾付款。"
                if is_bounty else action), acceptance=[acceptance]
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
