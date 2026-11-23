#!/usr/bin/env python3
"""Bounded read-only GitHub Actions run evidence for source/provider publisher census.

A successful GitHub run is NEVER treated as successful production deployment.
This script is a triage join, not a verifier of credentials or external effects.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode


def fetch_recent_runs(repo: str, since: str, max_pages: int = 30, branch: str | None = None):
    if len(repo.split("/")) != 2 or any(not part for part in repo.split("/")):
        raise ValueError("invalid repository")
    runs = []
    incomplete = False
    total = None
    for page in range(1, max_pages + 1):
        params = {"per_page": 100, "page": page, "created": ">=" + since}
        if branch:
            params["branch"] = branch
        query = urlencode(params)
        output = subprocess.check_output(
            ["gh", "api", f"repos/{repo}/actions/runs?{query}"],
            text=True, timeout=30,
        )
        data = json.loads(output)
        rows = data.get("workflow_runs")
        if not isinstance(rows, list):
            raise ValueError("workflow run response missing rows")
        if total is None:
            total = data.get("total_count")
        runs.extend(rows)
        if len(rows) < 100:
            break
    # GitHub may stop at a hard result-window cap while total_count still
    # exceeds the items returned. A short last page is not completeness proof.
    incomplete = bool(total is None or total > len(runs))
    return runs, incomplete, total


def build_evidence(provider: dict, runs: list[dict], since: str,
                   incomplete: bool, total: int | None):
    by_id = {}
    for entry in provider.get("workflows", []):
        if isinstance(entry.get("workflow_id"), int):
            by_id[entry["workflow_id"]] = entry
    for entry in provider.get("provider_not_in_either_branch", []):
        if isinstance(entry.get("workflow_id"), int):
            by_id.setdefault(entry["workflow_id"], entry)

    observations = defaultdict(lambda: {
        "runs_in_window": 0,
        "legacy_branch_runs": 0,
        "legacy_push_runs": 0,
        "legacy_manual_runs": 0,
        "other_branch_runs": 0,
        "completed_successful_runs": 0,
        "recent_first_seen": None,
        "recent_last_seen": None,
    })
    unmatched_runs = 0
    for run in runs:
        workflow_id = run.get("workflow_id")
        if not isinstance(workflow_id, int) or workflow_id not in by_id:
            unmatched_runs += 1
            continue
        obs = observations[workflow_id]
        obs["runs_in_window"] += 1
        branch = run.get("head_branch")
        event = run.get("event")
        if branch == "core/integration":
            obs["legacy_branch_runs"] += 1
            if event == "push":
                obs["legacy_push_runs"] += 1
            if event == "workflow_dispatch":
                obs["legacy_manual_runs"] += 1
        else:
            obs["other_branch_runs"] += 1
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            obs["completed_successful_runs"] += 1
        created = run.get("created_at")
        if isinstance(created, str):
            if obs["recent_first_seen"] is None or created < obs["recent_first_seen"]:
                obs["recent_first_seen"] = created
            if obs["recent_last_seen"] is None or created > obs["recent_last_seen"]:
                obs["recent_last_seen"] = created

    records = []
    for workflow_id, item in sorted(by_id.items()):
        obs = dict(observations.get(workflow_id, {}))
        source_is_legacy_push = bool(item.get("legacy_push"))
        mutating = bool(item.get("mutating_signal"))
        priority = (
            "p0_observed_legacy_push_candidate"
            if source_is_legacy_push and mutating and obs.get("legacy_push_runs", 0) > 0
            else "p1_observed_legacy_candidate"
            if source_is_legacy_push and mutating and obs.get("legacy_branch_runs", 0) > 0
            else "p2_unobserved_legacy_candidate"
            if source_is_legacy_push and mutating
            else "p3_other_review"
        )
        records.append({
            "workflow_id": workflow_id,
            "path": item["path"],
            "provider_state": item.get("provider_state"),
            "static_legacy_push": source_is_legacy_push,
            "static_mutating_signal": mutating,
            "priority": priority,
            **obs,
        })
    counts = Counter(x["priority"] for x in records)
    return {
        "schema": "agentos.workflow-recent-run-triage/v1",
        "disclaimer": "Successful Actions run != successful external deployment. No recent run != disabled workflow.",
        "since_date": since,
        "run_rows_observed": len(runs),
        "provider_run_total_reported": total,
        "pagination_incomplete": incomplete,
        "runs_unmatched_to_provider_inventory": unmatched_runs,
        "priority_counts": dict(sorted(counts.items())),
        "candidate_recent_legacy_push_count": counts["p0_observed_legacy_push_candidate"],
        "candidate_recent_legacy_nonpush_count": counts["p1_observed_legacy_candidate"],
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.days <= 90 or not 1 <= args.max_pages <= 60:
        raise SystemExit("run_history_window_out_of_bounds")
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).date().isoformat()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    general_runs, general_incomplete, general_total = fetch_recent_runs(
        repo, since, args.max_pages
    )
    legacy_runs, legacy_incomplete, legacy_total = fetch_recent_runs(
        repo, since, args.max_pages, branch="core/integration"
    )
    # Distinct query windows prevent high-volume main PR traffic from hiding
    # older core/integration runs. Merge by provider's immutable run ID.
    merged = {}
    for run in [*general_runs, *legacy_runs]:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            raise SystemExit("workflow_history_missing_run_id")
        merged[run_id] = run
    runs = list(merged.values())
    incomplete = general_incomplete or legacy_incomplete
    provider = json.loads(args.provider.read_text(encoding="utf-8"))
    evidence = build_evidence(provider, runs, since, incomplete, general_total)
    evidence["query_windows"] = {
        "all": {"observed": len(general_runs), "reported": general_total,
                "incomplete": general_incomplete},
        "core_integration": {"observed": len(legacy_runs),
                             "reported": legacy_total,
                             "incomplete": legacy_incomplete},
    }
    evidence["legacy_branch_run_rows_observed"] = sum(
        run.get("head_branch") == "core/integration" for run in runs
    )
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    for key in ("run_rows_observed", "legacy_branch_run_rows_observed", "pagination_incomplete",
                "candidate_recent_legacy_push_count",
                "candidate_recent_legacy_nonpush_count"):
        print(f"workflow_history_{key}={evidence[key]}")
    # Fail closed for unreliable input, not for bounded/truncated history:
    # truncation is explicitly recorded and no absence claim is permitted.
    if not provider.get("workflows"):
        raise SystemExit("workflow_history_missing_provider_inventory")


if __name__ == "__main__":
    main()
