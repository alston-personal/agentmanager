"""Fail-closed mainline freshness preflight for AgentOS code-task resume.

This is a reusable check for Runtime/Executor and PR CI, not an authority to
merge, rebase, retire production core/integration, or approve legacy releases.
It examines *Git history* at a verified remote tracking ref, never a model's
memory, project notes, or local branch name alone.

Exit 0 only when the source contains the pinned current main HEAD (or when
a caller explicitly requests read-only discovery). Legacy production tasks
are classified for a separate governed authorization, never auto-approved.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess

_SHA = re.compile(r"^[0-9a-f]{40}$")


class FreshnessError(RuntimeError):
    pass


def _git(root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=True,
        timeout=15, check=False,
    )
    if result.returncode:
        raise FreshnessError("GIT_EVIDENCE_UNAVAILABLE")
    return result.stdout.strip()


def inspect(*, root: str, main_ref: str, work_ref: str, kind: str) -> dict:
    if kind not in {"code", "read_only", "legacy_production"}:
        raise FreshnessError("INVALID_TASK_KIND")
    # Refs are fixed by a trusted caller. Do not accept Git CLI options or
    # arbitrary shell from the task/model payload.
    if main_ref != "refs/remotes/origin/main":
        raise FreshnessError("UNTRUSTED_MAIN_REF")
    if not _SHA.fullmatch(work_ref):
        raise FreshnessError("UNPINNED_WORK_SHA")
    main_sha = _git(root, "rev-parse", "--verify", main_ref + "^{commit}")
    if not _SHA.fullmatch(main_sha):
        raise FreshnessError("INVALID_MAIN_SHA")
    work_sha = _git(root, "rev-parse", "--verify", work_ref + "^{commit}")
    if work_sha != work_ref:
        raise FreshnessError("WORK_SHA_MISMATCH")
    common = _git(root, "merge-base", main_sha, work_sha)
    if not _SHA.fullmatch(common):
        raise FreshnessError("INVALID_MERGE_BASE")
    fresh = common == main_sha
    if kind == "read_only":
        status = "READ_ONLY_INSPECT"
        permitted = True
    elif kind == "legacy_production":
        status = "GOVERNED_LEGACY_EXCEPTION_REQUIRED"
        permitted = False
    else:
        status = "MAINLINE_CURRENT" if fresh else "RECONCILE_REQUIRED"
        permitted = fresh
    return {
        "schema": "agentos.branch-resume-gate/v1",
        "main_sha": main_sha,
        "work_sha": work_sha,
        "merge_base_sha": common,
        "kind": kind,
        "status": status,
        "allowed": permitted,
        "main_ancestor_of_work": fresh,
        "production_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--main-ref", default="refs/remotes/origin/main")
    parser.add_argument("--work-sha", required=True)
    parser.add_argument("--kind", required=True, choices=("code", "read_only", "legacy_production"))
    args = parser.parse_args()
    try:
        report = inspect(root=args.repo, main_ref=args.main_ref,
                         work_ref=args.work_sha, kind=args.kind)
    except (FreshnessError, subprocess.TimeoutExpired, OSError) as exc:
        report = {"schema": "agentos.branch-resume-gate/v1",
                  "status": "EVIDENCE_UNAVAILABLE",
                  "reason": str(exc) if isinstance(exc, FreshnessError) else "GIT_EVIDENCE_UNAVAILABLE",
                  "allowed": False, "production_authorized": False}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
