"""Produce an auditable local commit from a bounded, verified Paw candidate.

Never pushes, merges, publishes, invokes a shell or grants independent Claw PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos_node.paw_engineering_worktree import (
    PreparedPawWorktree, PawWorktreeBoundaryError, _git,
)
from agentos_node.paw_engineering_candidate import PawCandidateReceipt


@dataclass(frozen=True)
class PawLocalCommitReceipt:
    schema: str
    work_id: str
    base_sha: str
    commit_sha: str
    branch: str
    changed_file: str
    independent_acceptance_pass: bool = False
    published: bool = False


def commit_verified_paw_candidate(
    worktree: PreparedPawWorktree,
    candidate: PawCandidateReceipt,
    *,
    work_id: str,
) -> PawLocalCommitReceipt:
    root = Path(worktree.path).resolve(strict=True)
    if work_id != worktree.branch.removeprefix("paw/470/"):
        raise PawWorktreeBoundaryError("paw_commit_work_id_mismatch")
    if candidate.branch != worktree.branch or candidate.base_sha != worktree.base_sha:
        raise PawWorktreeBoundaryError("paw_commit_candidate_scope_mismatch")
    if not candidate.test_pass or candidate.test_exit_code != 0 or candidate.independent_acceptance_pass:
        raise PawWorktreeBoundaryError("paw_commit_candidate_unverified")
    if _git(root, "rev-parse", "--show-toplevel") != str(root):
        raise PawWorktreeBoundaryError("paw_commit_root_invalid")
    if _git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != worktree.branch:
        raise PawWorktreeBoundaryError("paw_commit_branch_mismatch")
    if _git(root, "rev-parse", "HEAD") != worktree.base_sha:
        raise PawWorktreeBoundaryError("paw_commit_base_mismatch")
    files = _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    allowed = "tests/test_paw_engineering_worktree.py"
    if len(files) != 1 or files[0] != "M " + allowed or candidate.changed_file != allowed:
        raise PawWorktreeBoundaryError("paw_commit_changed_files_not_authorized")
    import hashlib
    actual_hash = hashlib.sha256((root / allowed).read_bytes()).hexdigest()
    if actual_hash != candidate.content_sha256:
        raise PawWorktreeBoundaryError("paw_commit_candidate_hash_mismatch")
    _git(root, "diff", "--check")
    _git(root, "-c", "user.name=AgentOS Paw", "-c", "user.email=paw@users.noreply.github.com",
         "add", "--", allowed)
    # Absolute explicit path and fixed message; no shell or arbitrary command selection.
    _git(root, "-c", "user.name=AgentOS Paw", "-c", "user.email=paw@users.noreply.github.com",
         "commit", "-m", "test(paw-470): bounded candidate " + work_id,
         "--only", "--", allowed)
    sha = _git(root, "rev-parse", "HEAD")
    if _git(root, "status", "--porcelain"):
        raise PawWorktreeBoundaryError("paw_commit_postcondition_dirty")
    if _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha) != allowed:
        raise PawWorktreeBoundaryError("paw_commit_postcondition_scope_mismatch")
    return PawLocalCommitReceipt(
        schema="agentos.paw-local-commit-receipt/v1", work_id=work_id,
        base_sha=worktree.base_sha, commit_sha=sha, branch=worktree.branch,
        changed_file=allowed,
    )
