#!/usr/bin/env python3
"""Read-only branch-convergence changed-path classifier.
This script is a review gate, NOT production execution authority.
Inputs: newline-delimited repo-relative changed paths on stdin.
"""
import argparse
import json
import sys
from pathlib import PurePosixPath

RED_PREFIXES = (
    ".agent/", ".agentos/", ".github/workflows/",
    "agent_core/", "agentos/core/", "core/", "one/", "supervisor/",
    "executor/", "node/", "agentos_node/", "scripts/deploy_",
    "scripts/check_", "docs/CORE_DEPLOYMENT",
)
RED_EXACT = {".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"}
AMBER_PREFIXES = ("tests/", "dashboard/", "scripts/", "services/", "apps/", "studio/", "docs/")
GREEN_PREFIXES = ("content/", "stories/", "research/", "examples/")

def classify(path):
    p = path.strip()
    if not p or p.startswith("/") or "\\" in p or ".." in PurePosixPath(p).parts:
        return "INVALID"
    if p in RED_EXACT or any(p.startswith(pre) for pre in RED_PREFIXES):
        return "RED"
    if any(p.startswith(pre) for pre in AMBER_PREFIXES):
        return "AMBER"
    if any(p.startswith(pre) for pre in GREEN_PREFIXES):
        return "GREEN"
    return "UNKNOWN"

def audit(paths):
    entries = [{"path": p, "risk": classify(p)} for p in sorted(set(paths)) if p.strip()]
    summary = {key: sum(x["risk"] == key for x in entries)
               for key in ("RED", "AMBER", "GREEN", "UNKNOWN", "INVALID")}
    return {"schema": "agentos.branch-path-risk/v1",
            "entries": entries, "summary": summary,
            "requires_governed_review": bool(summary["RED"] or summary["UNKNOWN"] or summary["INVALID"])}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-review", action="store_true",
                        help="Fail on RED/UNKNOWN/INVALID until review is recorded by an external authoritative gate")
    args = parser.parse_args()
    report = audit(sys.stdin.read().splitlines())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.fail_on_review and report["requires_governed_review"]:
        sys.exit(2)
