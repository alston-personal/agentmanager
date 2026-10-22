"""Bounded, preparation-only engineering worktree for The Paw.

No LLM, shell, provider, credentials, commits, push, merge or deploy happens here.
A separately authorized executor must consume the returned worktree and be
independently verified. The function cannot be called by ONE model input.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPOSITORY = "alston-personal/agentmanager"
BRANCH_PREFIX = "paw/470/"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


class PawWorktreeBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedPawWorktree:
    path: Path
    branch: str
    base_sha: str
    mutation_performed: bool = False
    independent_acceptance_pass: bool = False


def _git(repository: Path, *args: str) -> str:
    try:
        p = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True, capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise PawWorktreeBoundaryError("paw_git_preparation_failed") from exc
    return p.stdout.strip()


def prepare_paw_worktree(
    *, repository: Path, workspace_root: Path, work_id: str,
    base_sha: str, repository_id: str = REPOSITORY,
) -> PreparedPawWorktree:
    """Create exactly one local isolated branch/worktree, with no code execution."""
    if repository_id != REPOSITORY or not _ID.fullmatch(work_id):
        raise PawWorktreeBoundaryError("paw_work_scope_not_authorized")
    if not _SHA.fullmatch(base_sha):
        raise PawWorktreeBoundaryError("paw_base_commit_invalid")
    repository = Path(repository).resolve(strict=True)
    workspace_root = Path(workspace_root).resolve(strict=True)
    if repository == workspace_root or repository in workspace_root.parents or workspace_root in repository.parents:
        raise PawWorktreeBoundaryError("paw_worktree_root_not_isolated")
    if workspace_root.is_symlink() or repository.is_symlink():
        raise PawWorktreeBoundaryError("paw_symlink_not_authorized")
    if _git(repository, "rev-parse", "--is-bare-repository") != "false":
        raise PawWorktreeBoundaryError("paw_repository_invalid")
    if _git(repository, "status", "--porcelain"):
        raise PawWorktreeBoundaryError("paw_repository_dirty")
    if _git(repository, "rev-parse", "--verify", "HEAD") != base_sha:
        raise PawWorktreeBoundaryError("paw_base_not_current_head")
    branch = BRANCH_PREFIX + work_id
    target = workspace_root / work_id
    if target.exists() or target.is_symlink():
        raise PawWorktreeBoundaryError("paw_existing_workspace_requires_reconciliation")
    if _git(repository, "branch", "--list", branch):
        raise PawWorktreeBoundaryError("paw_existing_branch_requires_reconciliation")
    _git(repository, "worktree", "add", "-b", branch, str(target), base_sha)
    if _git(target, "rev-parse", "--verify", "HEAD") != base_sha:
        raise PawWorktreeBoundaryError("paw_worktree_base_mismatch")
    return PreparedPawWorktree(target, branch, base_sha)
