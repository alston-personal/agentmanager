#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

DEFAULT_POLICY_FILE = Path(__file__).resolve().parents[1] / "governance" / "project-release-lanes.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def load_policy(path: Path | str = DEFAULT_POLICY_FILE) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "agentos.project-release-lanes/v1":
        raise ValueError("unsupported_project_release_lane_schema")
    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("project_release_lane_projects_missing")
    return data


def _exact_sha_required(config: dict[str, Any], candidate_sha: str | None) -> tuple[bool, str]:
    if not config.get("require_exact_source_sha", False):
        return True, "exact_source_sha_not_required"
    if not candidate_sha:
        return False, "exact_source_sha_required"
    if not SHA40.fullmatch(candidate_sha):
        return False, "exact_source_sha_invalid"
    return True, "exact_source_sha_valid"


def decide(
    policy: dict[str, Any],
    project: str,
    action: str,
    target_branch: str,
    *,
    explicit_human_approval: bool = False,
    candidate_sha: str | None = None,
) -> tuple[bool, str]:
    project_policy = policy["projects"].get(project)
    if not isinstance(project_policy, dict):
        return False, "unknown_project"

    promotion_branch = project_policy.get("promotion_branch")
    development_patterns = project_policy.get("development_branch_patterns", [])

    if action == "development_write":
        if target_branch == promotion_branch:
            return False, "development_write_to_promotion_branch_denied"
        if any(fnmatch(target_branch, pattern) for pattern in development_patterns):
            return True, "development_lane_allowed"
        return False, "branch_not_in_development_lane"

    if action == "promotion":
        if target_branch != promotion_branch:
            return False, "promotion_target_must_be_promotion_branch"
        requires = project_policy.get("promotion_requires", {})
        if requires.get("explicit_human_approval", False) and not explicit_human_approval:
            return False, "explicit_human_approval_required"
        return True, "promotion_allowed"

    if action in {"poc_deploy", "production_deploy"}:
        environment = "poc" if action == "poc_deploy" else "production"
        config = project_policy.get("deployment", {}).get(environment)
        if not isinstance(config, dict):
            return False, f"{environment}_deployment_not_configured"
        if target_branch != config.get("source_branch"):
            return False, f"{environment}_requires_configured_source_branch"
        sha_ok, sha_reason = _exact_sha_required(config, candidate_sha)
        if not sha_ok:
            return False, sha_reason
        return True, f"{environment}_candidate_allowed"

    return False, "unknown_action"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-file", default=str(DEFAULT_POLICY_FILE))
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--action",
        required=True,
        choices=["development_write", "promotion", "poc_deploy", "production_deploy"],
    )
    parser.add_argument("--target-branch", required=True)
    parser.add_argument("--candidate-sha")
    parser.add_argument("--explicit-human-approval", action="store_true")
    args = parser.parse_args()

    try:
        policy = load_policy(args.policy_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PROJECT_RELEASE_LANE=DENY reason=policy_load_failed detail={exc}")
        return 2

    allowed, reason = decide(
        policy,
        args.project,
        args.action,
        args.target_branch,
        explicit_human_approval=args.explicit_human_approval,
        candidate_sha=args.candidate_sha,
    )
    print(f"PROJECT_RELEASE_LANE={'ALLOW' if allowed else 'DENY'} reason={reason}")
    return 0 if allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
