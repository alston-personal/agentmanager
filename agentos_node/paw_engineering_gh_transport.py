"""Opt-in authenticated GitHub CLI transport for the bounded Paw publisher.

Run only inside a separately trusted publisher process with a preconfigured
GitHub App identity. Do not invoke from wake capsules or untrusted model input.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
from agentos_node.paw_engineering_publisher import publish_paw_draft, REPO, BASE
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError, _git


def publish_with_trusted_gh(
    local: PawLocalCommitReceipt, *, worktree: Path,
    authenticated_publisher: bool,
):
    if not authenticated_publisher:
        raise PawWorktreeBoundaryError("paw_publisher_not_authorized")
    root = Path(worktree).resolve(strict=True)
    if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != local.branch:
        raise PawWorktreeBoundaryError("paw_publisher_branch_mismatch")
    if _git(root, "rev-parse", "HEAD") != local.commit_sha:
        raise PawWorktreeBoundaryError("paw_publisher_head_mismatch")
    if _git(root, "status", "--porcelain"):
        raise PawWorktreeBoundaryError("paw_publisher_dirty_checkout")
    remote = _git(root, "remote", "get-url", "origin")
    if remote not in (
        "https://github.com/" + REPO + ".git",
        "git@github.com:" + REPO + ".git",
    ):
        raise PawWorktreeBoundaryError("paw_publisher_remote_mismatch")

    # Reject injected Git configuration before any network or privileged Git operation.
    if any(k.startswith(('GIT_CONFIG_', 'GIT_TRACE', 'GIT_EXEC_PATH')) or k in ('GIT_SSH', 'GIT_SSH_COMMAND', 'GIT_ASKPASS', 'GIT_TEMPLATE_DIR') for k in os.environ):
        raise PawWorktreeBoundaryError('paw_publisher_git_environment_untrusted')

    # Git aliases/remote push URLs are mutable in the worker worktree. Never
    # let origin.pushurl redirect an authenticated publisher to another host.
    push_url = _git(root, "remote", "get-url", "--push", "origin")
    if push_url != "https://github.com/" + REPO + ".git":
        raise PawWorktreeBoundaryError("paw_publisher_push_target_invalid")

    def gh(*args):
        p = subprocess.run(
            ["gh", *args], cwd=root, stdin=subprocess.DEVNULL,
            text=True, capture_output=True, timeout=45, check=False,
        )
        if p.returncode:
            raise PawWorktreeBoundaryError("paw_publisher_github_operation_failed")
        return p.stdout.strip()

    def normalize(raw):
        return {
            "repo": REPO, "head": raw["headRefName"],
            "head_sha": raw["headRefOid"],
            "base": raw["baseRefName"], "draft": raw["isDraft"],
            "merged": raw["state"] == "MERGED", "number": raw["number"],
            "url": raw["url"],
        }

    def lookup(repo, branch):
        raw = json.loads(gh(
            "pr", "list", "--repo", REPO, "--state", "open",
            "--head", branch, "--json",
            "number,url,headRefName,headRefOid,baseRefName,isDraft,state",
        ))
        if len(raw) > 1:
            raise PawWorktreeBoundaryError("paw_publisher_duplicate_remote_pr")
        return normalize(raw[0]) if raw else None

    def push(branch, sha):
        # Exact source and destination; never force-push or target main.
        p = subprocess.run(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", "push", "origin",
             sha + ":refs/heads/" + branch],
            stdin=subprocess.DEVNULL, text=True, capture_output=True,
            timeout=60, check=False,
        )
        if p.returncode:
            raise PawWorktreeBoundaryError("paw_publisher_push_failed")

    def create(repo, head, base):
        gh(
            "pr", "create", "--repo", REPO, "--draft",
            "--base", BASE, "--head", head,
            "--title", "test(#470): bounded Paw candidate " + local.work_id,
            "--body", "Automated bounded Paw candidate. Requires independent Claw review; no auto-merge.",
        )
        found = lookup(repo, head)
        if found is None:
            raise PawWorktreeBoundaryError("paw_publisher_pr_missing_after_create")
        return found

    return publish_paw_draft(
        local, lookup_pr=lookup, publish_branch=push,
        create_draft_pr=create, authenticated_publisher=True,
    )
