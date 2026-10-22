"""Bounded local Paw patch candidate and deterministic verification.

Not wired to ONE or model authority. Only fixed test artifacts may be edited.
This is an acceptance-candidate receipt, never Claw verification or DONE.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentos_node.paw_engineering_worktree import PreparedPawWorktree, PawWorktreeBoundaryError

_ALLOWED = frozenset({"tests/test_paw_engineering_worktree.py"})
_MAX_BYTES = 32_768


@dataclass(frozen=True)
class PawCandidateReceipt:
    branch: str
    base_sha: str
    changed_file: str
    content_sha256: str
    test_exit_code: int
    test_pass: bool
    independent_acceptance_pass: bool = False


def apply_bounded_test_candidate(
    worktree: PreparedPawWorktree, *, relative_path: str,
    expected_sha256: str, replacement: str,
) -> PawCandidateReceipt:
    if relative_path not in _ALLOWED:
        raise PawWorktreeBoundaryError("paw_patch_path_not_authorized")
    if not isinstance(replacement, str) or len(replacement.encode("utf-8")) > _MAX_BYTES:
        raise PawWorktreeBoundaryError("paw_patch_size_invalid")
    root = worktree.path.resolve(strict=True)
    target = root / relative_path
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
        raise PawWorktreeBoundaryError("paw_patch_target_invalid")
    before = target.read_bytes()
    if hashlib.sha256(before).hexdigest() != expected_sha256:
        raise PawWorktreeBoundaryError("paw_patch_base_mismatch")
    # Refuse modifying any worktree with pre-existing edits.
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                            capture_output=True, text=True, check=True, timeout=10)
    if status.stdout.strip():
        raise PawWorktreeBoundaryError("paw_patch_worktree_dirty")
    # Syntax check before making any candidate changes; no shell or model command.
    compile(replacement, relative_path, "exec")
    target.write_text(replacement, encoding="utf-8")
    diff = subprocess.run(["git", "-C", str(root), "diff", "--check"],
                          capture_output=True, text=True, timeout=10)
    if diff.returncode:
        target.write_bytes(before)
        raise PawWorktreeBoundaryError("paw_patch_diff_check_failed")
    test = subprocess.run(["python3", "-m", "pytest", "-q", relative_path],
                          cwd=root, capture_output=True, text=True, timeout=120)
    return PawCandidateReceipt(
        branch=worktree.branch, base_sha=worktree.base_sha,
        changed_file=relative_path,
        content_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        test_exit_code=test.returncode, test_pass=test.returncode == 0,
    )
