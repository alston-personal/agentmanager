"""Trusted Oracle-side Git evidence for AgentOS code Executor claim/resume.

The Runtime owner, not the model-provided job, configures which *actual* local
worktree each registered engineering job will execute. The worktree must be
the same source root used by its Executor. This module neither authorizes a
release nor changes branches, worktrees, or Node identities.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import subprocess

from scripts.branch_resume_guard import FreshnessError, inspect


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FreshnessError("HOST_GIT_UNAVAILABLE") from exc
    if proc.returncode:
        raise FreshnessError("HOST_GIT_EVIDENCE_UNAVAILABLE")
    return proc.stdout.strip()


class LocalCodeResumeProbe:
    """Worktree mapping is host-provisioned and must match Executor checkout.

    The configured origin URL is itself an operator-owned trust pin. Fetching
    the current remote main at dispatch time avoids indefinitely trusting
    stale refs/remotes/origin/main. The trusted caller MUST not accept
    `worktrees` or `origin_url` from an untrusted Executor/IR payload.
    """

    def __init__(self, *, worktrees: Mapping[str, str | Path], origin_url: str):
        if not origin_url or not isinstance(origin_url, str):
            raise ValueError("trusted_origin_url_required")
        if not isinstance(worktrees, Mapping) or not worktrees:
            raise ValueError("trusted_worktree_mapping_required")
        self._worktrees = {k: Path(v).resolve(strict=True)
                           for k, v in worktrees.items()}
        self._origin_url = origin_url
        if not all(isinstance(k, str) and k.startswith("engineering.") and p.is_dir()
                   for k, p in self._worktrees.items()):
            raise ValueError("invalid_trusted_worktree_mapping")

    def __call__(self, spec) -> dict:
        if getattr(spec, "authority", None) != "bounded-code-fix":
            raise FreshnessError("NOT_A_CODE_FIX_JOB")
        root = self._worktrees.get(getattr(spec, "job_type", None))
        if root is None:
            raise FreshnessError("WORKTREE_NOT_REGISTERED")
        if _git(root, "remote", "get-url", "origin") != self._origin_url:
            raise FreshnessError("UNTRUSTED_WORKTREE_ORIGIN")
        # Require the registered worktree root, not a nested unrelated repo.
        if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise FreshnessError("WORKTREE_ROOT_MISMATCH")
        # An uncommitted local edit is not covered by SHA ancestry evidence.
        if _git(root, "status", "--porcelain", "--untracked-files=normal"):
            raise FreshnessError("WORKTREE_DIRTY")
        # Read remote main into FETCH_HEAD. No checkout, reset, merge or push.
        _git(root, "fetch", "--no-tags", "origin", "main")
        work_sha = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        return inspect(root=str(root), main_ref="FETCH_HEAD",
                       work_ref=work_sha, kind="code")
