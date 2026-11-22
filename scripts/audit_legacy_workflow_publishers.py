#!/usr/bin/env python3
"""Read-only, whole-tree legacy GitHub Actions publisher inventory.

Static signals are triage evidence, never proof of live deployment or safety.
No network calls, subprocesses, secret values, or repository mutations.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import re
from collections import Counter
from pathlib import Path

import yaml


MUTATION_RULES = {
    "agentos_mutating_dispatch": re.compile(
        r"agentos_dispatch\.sh\s+[\w.:-]+\s+"
        r"(?:repair|deploy|restart|install|rollout|provision|start|stop|submit|write|approve)\b",
        re.I,
    ),
    "service_mutation": re.compile(
        r"\b(?:systemctl|service)\b[^\n]{0,100}\b"
        r"(?:restart|start|stop|enable|disable|daemon-reload)\b", re.I,
    ),
    "git_push": re.compile(r"\bgit\s+(?:-[^\s]+\s+)*push\b", re.I),
    "deploy_or_install_script": re.compile(
        r"\b(?:bash|sh|python3?|sudo)\b[^\n]{0,150}"
        r"(?:scripts/)?(?:install|deploy|repair|rollout|converge|quarantine)[\w./-]*\.(?:sh|py)\b",
        re.I,
    ),
    "remote_shell": re.compile(r"\bssh\b[^\n]{0,300}\bbash\s+-s\b", re.I),
    "workflow_dispatch_api": re.compile(
        r"\bgh\s+(?:workflow\s+run|api\s+[^\n]{0,150}/dispatches)\b", re.I
    ),
    "remote_mutation_api": re.compile(
        r"\b(?:curl|gh\s+api)\b[^\n]{0,250}"
        r"(?:-X\s*(?:POST|PUT|PATCH|DELETE)|-f\s+\w+=|--method\s+(?:POST|PUT|PATCH|DELETE))\b",
        re.I,
    ),
    "deployment_commands": re.compile(
        r"\b(?:kubectl\s+(?:apply|rollout|delete)|helm\s+(?:upgrade|install)|"
        r"ansible-playbook|docker\s+compose\s+up|npm\s+run\s+deploy)\b", re.I
    ),
}
REVIEW_RULES = {
    "remote_access": re.compile(r"\b(?:ssh|scp|rsync)\b", re.I),
    "dispatch_unspecified": re.compile(r"agentos_dispatch\.sh|workflow_dispatch", re.I),
    "execution_or_write": re.compile(
        r"\b(?:sudo|curl|wget|git\s+reset|git\s+checkout|"
        r"subprocess\.(?:run|Popen)|os\.system)\b", re.I
    ),
}
WORKFLOWS = ".github/workflows/"
AUTOMATIC = {
    "push", "schedule", "workflow_run", "repository_dispatch",
    "issue_comment", "issues", "pull_request", "pull_request_target",
    "release", "create", "delete", "deployment", "deployment_status",
}
KNOWN_MANUAL = {"workflow_dispatch"}
KNOWN_REUSABLE = {"workflow_call"}


def events(value):
    if isinstance(value, dict):
        return sorted(str(k) for k in value)
    if isinstance(value, list):
        return sorted(str(v) for v in value)
    if isinstance(value, str):
        return [value]
    return []


def scan(root: Path):
    rows = []
    links = {}
    for path in sorted((root / WORKFLOWS).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".yml", ".yaml"):
            continue
        rel = path.relative_to(root).as_posix()
        row = {
            "path": rel, "source_sha256": sha256(path.read_bytes()).hexdigest(), "events": [], "signals": [], "review_signals": [],
            "called_workflows": [], "parse_error": None, "job_count": 0,
            "active_trigger": False, "automatic_trigger": False,
            "manual_trigger": False, "reusable_trigger": False,
        }
        try:
            doc = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            if not isinstance(doc, dict):
                raise ValueError("workflow root is not mapping")
            row["events"] = events(doc.get("on", []))
            rows_jobs = doc.get("jobs") or {}
            if not isinstance(rows_jobs, dict):
                raise ValueError("jobs must be mapping")
            row["job_count"] = len(rows_jobs)
            signals, review, children = set(), set(), set()
            for job in rows_jobs.values():
                if not isinstance(job, dict):
                    continue
                steps = (job.get("steps") or [])
                if not isinstance(steps, list):
                    steps = []
                for step in [job, *steps]:
                    if not isinstance(step, dict):
                        continue
                    use = str(step.get("uses") or "")
                    run = step.get("run")
                    if use.startswith("./.github/workflows/"):
                        children.add(use.split("@", 1)[0][2:])
                    elif use and re.search(r"(?:ssh-action|scp-action|github-script|create-pull-request)", use, re.I):
                        review.add("potentially_mutating_action")
                    if isinstance(run, str):
                        for key, pattern in MUTATION_RULES.items():
                            if pattern.search(run):
                                signals.add(key)
                        for key, pattern in REVIEW_RULES.items():
                            if pattern.search(run):
                                review.add(key)
            row["signals"] = sorted(signals)
            row["review_signals"] = sorted(review)
            row["called_workflows"] = sorted(children)
        except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError) as exc:
            row["parse_error"] = type(exc).__name__
        row["automatic_trigger"] = any(e in AUTOMATIC for e in row["events"])
        row["manual_trigger"] = any(e in KNOWN_MANUAL for e in row["events"])
        row["reusable_trigger"] = any(e in KNOWN_REUSABLE for e in row["events"])
        row["active_trigger"] = bool(row["events"])
        rows.append(row)
        links[rel] = row

    # One hop per iteration propagates local reusable workflow risks to callers.
    for _ in range(len(rows)):
        changed = False
        for row in rows:
            old = set(row["signals"])
            for path in row["called_workflows"]:
                callee = links.get(path)
                if callee:
                    old.update(callee["signals"])
            updated = sorted(old)
            if updated != row["signals"]:
                row["signals"] = updated
                changed = True
        if not changed:
            break

    for row in rows:
        if row["parse_error"]:
            row["classification"] = "unreadable_review_required"
        elif row["signals"]:
            row["classification"] = "mutating_signal"
        elif row["review_signals"] or row["called_workflows"]:
            row["classification"] = "manual_review_required"
        else:
            row["classification"] = "no_mutating_signal_observed"
        row["is_active_workflow_path"] = row["path"].count("/") == 2
        row["legacy_push"] = (
            "push" in row["events"]
            and re.search(r"\bcore/integration\b",
                          (root / row["path"]).read_text(encoding="utf-8").split("\njobs:", 1)[0])
            is not None
        )
    return rows


def report(rows):
    groups = Counter(r["classification"] for r in rows)
    triggers = Counter()
    for r in rows:
        triggers.update(r["events"])
    priority = [
        r["path"] for r in rows
        if r["classification"] == "mutating_signal"
        and (r["legacy_push"] or r["manual_trigger"] or r["reusable_trigger"])
    ]
    unknown = [r["path"] for r in rows if r["classification"] == "unreadable_review_required"]
    return {
        "schema": "agentos.legacy-workflow-publisher-inventory/v1",
        "disclaimer": "Static candidate inventory; not provider enabled-state or live mutation proof",
        "workflow_count": len(rows),
        "root_workflow_count": sum(r["is_active_workflow_path"] for r in rows),
        "historical_nested_path_count": sum(not r["is_active_workflow_path"] for r in rows),
        "root_legacy_push_count": sum(
            r["is_active_workflow_path"] and r["legacy_push"] for r in rows
        ),
        "root_mutating_legacy_push_count": sum(
            r["is_active_workflow_path"] and r["legacy_push"]
            and r["classification"] == "mutating_signal" for r in rows
        ),
        "class_counts": dict(sorted(groups.items())),
        "event_counts": dict(sorted(triggers.items())),
        "legacy_push_count": sum(r["legacy_push"] for r in rows),
        "mutating_legacy_push_count": sum(
            r["legacy_push"] and r["classification"] == "mutating_signal" for r in rows
        ),
        "priority_review_count": len(priority),
        "priority_paths": priority,
        "unreadable_paths": unknown,
        "workflows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=0)
    args = parser.parse_args()
    rows = scan(args.root)
    result = report(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("legacy_workflows_total=" + str(len(rows)))
    print("legacy_root_workflows=" + str(result["root_workflow_count"]))
    print("legacy_history_archives=" + str(result["historical_nested_path_count"]))
    print("legacy_root_push=" + str(result["root_legacy_push_count"]))
    print("legacy_root_mutating_push=" + str(result["root_mutating_legacy_push_count"]))
    for name, value in sorted(result["class_counts"].items()):
        print("legacy_class_" + name + "=" + str(value))
    print("legacy_push=" + str(result["legacy_push_count"]))
    print("legacy_mutating_push=" + str(result["mutating_legacy_push_count"]))
    print("legacy_priority_review=" + str(result["priority_review_count"]))
    print("legacy_unreadable=" + str(len(result["unreadable_paths"])))
    if args.expected_count and len(rows) != args.expected_count:
        raise SystemExit("legacy_workflow_count_changed: inspect new tree first")
    if result["unreadable_paths"]:
        raise SystemExit("legacy_workflow_parse_incomplete")
    if not rows:
        raise SystemExit("legacy_workflow_inventory_empty")


if __name__ == "__main__":
    main()
