#!/usr/bin/env python3
"""Read-only GitHub Actions workflow provider-state census joined to source signals."""
import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path


def fetch_provider_workflows(repo: str):
    if not repo or "/" not in repo:
        raise ValueError("invalid repository name")
    result = []
    for page in range(1, 31):
        output = subprocess.check_output(
            ["gh", "api", f"repos/{repo}/actions/workflows?per_page=100&page={page}"],
            text=True, timeout=20,
        )
        data = json.loads(output)
        rows = data.get("workflows")
        if not isinstance(rows, list):
            raise ValueError("provider workflow list missing")
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise RuntimeError("provider_workflow_pagination_exceeded")


def merge_provider(source: dict, workflow_rows: list, main_source: dict | None = None):
    provider = {}
    for row in workflow_rows:
        path = row.get("path")
        state = row.get("state")
        if not isinstance(path, str) or not path.startswith(".github/workflows/"):
            continue
        if state not in {"active", "disabled_manually", "disabled_inactivity", "deleted"}:
            state = "unknown"
        provider[path] = {
            "provider_state": state,
            "workflow_id": row.get("id") if isinstance(row.get("id"), int) else None,
        }
    # The Actions provider may retain workflow identities whose source path
    # is absent from BOTH currently authoritative branches. Such records
    # require provider lifecycle review, not source-only inference.
    main_paths = {
        r["path"] for r in (main_source or {}).get("workflows", [])
        if r.get("is_active_workflow_path")
    }
    legacy_paths = {
        r["path"] for r in source.get("workflows", [])
        if r.get("is_active_workflow_path")
    }
    provider_extra = [
        {"path": path, **data}
        for path, data in sorted(provider.items())
        if path not in main_paths and path not in legacy_paths
    ]
    provider_extra_active = [
        r for r in provider_extra if r["provider_state"] == "active"
    ]
    records = []
    for row in source.get("workflows", []):
        if not row.get("is_active_workflow_path"):
            continue
        state = provider.get(row["path"], {"provider_state": "not_registered", "workflow_id": None})
        records.append({
            "path": row["path"],
            "provider_state": state["provider_state"],
            "workflow_id": state["workflow_id"],
            "legacy_push": bool(row.get("legacy_push")),
            "mutating_signal": row.get("classification") == "mutating_signal",
        })
    prioritized = [
        r for r in records if r["legacy_push"] and r["mutating_signal"]
    ]
    return {
        "schema": "agentos.github-workflow-provider-readonly/v1",
        "disclaimer": "Provider workflow enabled-state only; does not prove branch job reachability, credentials or actual execution",
        "provider_listed_workflows": len(workflow_rows),
        "provider_unique_paths": len(provider),
        "provider_not_in_either_branch": provider_extra,
        "provider_not_in_either_branch_active": provider_extra_active,
        "provider_not_in_either_branch_count": len(provider_extra),
        "provider_not_in_either_branch_active_count": len(provider_extra_active),
        "provider_all_state_counts": dict(sorted(Counter(
            "active" if row.get("state") == "active" else str(row.get("state") or "unknown")
            for row in workflow_rows
        ).items())),
        "source_root_workflows": len(records),
        "source_state_counts": dict(sorted(Counter(r["provider_state"] for r in records).items())),
        "legacy_push_mutating_state_counts": dict(sorted(
            Counter(r["provider_state"] for r in prioritized).items()
        )),
        "legacy_push_mutating_total": len(prioritized),
        "legacy_push_mutating_workflows": prioritized,
        "workflows": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--main", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    d = json.loads(args.source.read_text(encoding="utf-8"))
    main_source = (
        json.loads(args.main.read_text(encoding="utf-8"))
        if args.main else None
    )
    result = merge_provider(
        d, fetch_provider_workflows(os.environ.get("GITHUB_REPOSITORY", "")),
        main_source,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for key in ("provider_listed_workflows", "source_root_workflows",
                "legacy_push_mutating_total"):
        print("provider_" + key + "=" + str(result[key]))
    for key in ("provider_unique_paths", "provider_not_in_either_branch_count",
                "provider_not_in_either_branch_active_count"):
        print(key + "=" + str(result[key]))
    for name, value in result["legacy_push_mutating_state_counts"].items():
        print("provider_legacy_push_mutating_" + name + "=" + str(value))
    if result["legacy_push_mutating_total"] != d["root_mutating_legacy_push_count"]:
        raise SystemExit("source_provider_candidate_mismatch")


if __name__ == "__main__":
    main()
