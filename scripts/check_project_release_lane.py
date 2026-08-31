#!/usr/bin/env python3
from __future__ import annotations

import argparse
from fnmatch import fnmatch

POLICIES = {
    "layoutlib": {
        "repo": "alston-personal/layoutlib",
        "development": ["develop", "feature/*", "fix/*", "governance/*"],
        "promotion": "main",
    }
}


def decide(project: str, action: str, target_branch: str, explicit_human_approval: bool = False) -> tuple[bool, str]:
    p = POLICIES.get(project)
    if not p:
        return False, "unknown_project"
    if action == "development_write":
        if target_branch == p["promotion"]:
            return False, "development_write_to_promotion_branch_denied"
        if any(fnmatch(target_branch, pat) for pat in p["development"]):
            return True, "development_lane_allowed"
        return False, "branch_not_in_development_lane"
    if action == "promotion":
        if target_branch != p["promotion"]:
            return False, "promotion_target_must_be_promotion_branch"
        if not explicit_human_approval:
            return False, "explicit_human_approval_required"
        return True, "promotion_allowed"
    if action == "poc_deploy":
        if target_branch != "develop":
            return False, "poc_requires_develop_candidate"
        return True, "poc_candidate_allowed"
    if action == "production_deploy":
        if target_branch != p["promotion"]:
            return False, "production_requires_promoted_state"
        return True, "production_candidate_allowed"
    return False, "unknown_action"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--action", required=True, choices=["development_write", "promotion", "poc_deploy", "production_deploy"])
    ap.add_argument("--target-branch", required=True)
    ap.add_argument("--explicit-human-approval", action="store_true")
    args = ap.parse_args()
    ok, reason = decide(args.project, args.action, args.target_branch, args.explicit_human_approval)
    print(f"PROJECT_RELEASE_LANE={'ALLOW' if ok else 'DENY'} reason={reason}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
