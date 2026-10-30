"""Import an unprivileged Paw Git bundle into publisher-owned disposable storage.

This deliberately does not consume Worker worktrees or perform any network action.
The bundle ingress location and Unix ACL must be separately provisioned.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError, _ID, _SHA, BRANCH_PREFIX


def import_paw_bundle(*, bundle: Path, destination: Path, work_id: str, commit_sha: str) -> Path:
    if not isinstance(work_id, str) or not _ID.fullmatch(work_id):
        raise PawWorktreeBoundaryError("paw_bundle_work_id_invalid")
    if not isinstance(commit_sha, str) or not _SHA.fullmatch(commit_sha):
        raise PawWorktreeBoundaryError("paw_bundle_commit_invalid")
    bundle = Path(bundle)
    destination = Path(destination)
    if (not bundle.is_absolute() or bundle.is_symlink() or not bundle.is_file()
            or not destination.is_absolute() or destination.is_symlink()):
        raise PawWorktreeBoundaryError("paw_bundle_paths_invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    existed = destination.exists()
    if existed and (not destination.is_dir() or destination.is_symlink()):
        raise PawWorktreeBoundaryError("paw_bundle_paths_invalid")
    if not existed:
        destination.mkdir(mode=0o700)
    def git(*args):
        try:
            p = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", *args],
                cwd=destination, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=60, check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PawWorktreeBoundaryError("paw_bundle_import_failed") from exc
        return p.stdout.strip()
    if existed:
        if git("rev-parse", "--is-bare-repository") != "true":
            raise PawWorktreeBoundaryError("paw_bundle_existing_repository_invalid")
    else:
        git("init", "--bare", "-q")
    ref = BRANCH_PREFIX + work_id
    if existed:
        # An initialized repository without the requested ref is an interrupted
        # import. Re-fetch the immutable bundle; never overwrite another head.
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/heads/" + ref],
            cwd=destination, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=15, check=False,
        )
        if probe.returncode == 0:
            if probe.stdout.strip() != commit_sha:
                raise PawWorktreeBoundaryError("paw_bundle_existing_head_mismatch")
            return destination
    git("bundle", "verify", str(bundle))
    git("fetch", "--no-tags", str(bundle), "refs/heads/" + ref + ":refs/heads/" + ref)
    actual = git("rev-parse", "refs/heads/" + ref)
    if actual != commit_sha:
        raise PawWorktreeBoundaryError("paw_bundle_head_mismatch")
    return destination


def export_paw_bundle(*, worktree: Path, destination: Path, work_id: str, commit_sha: str) -> Path:
    """Write a single scoped branch bundle before durable Worker handoff."""
    if not isinstance(work_id, str) or not _ID.fullmatch(work_id):
        raise PawWorktreeBoundaryError("paw_bundle_work_id_invalid")
    if not isinstance(commit_sha, str) or not _SHA.fullmatch(commit_sha):
        raise PawWorktreeBoundaryError("paw_bundle_commit_invalid")
    worktree = Path(worktree)
    destination = Path(destination)
    if (not worktree.is_absolute() or worktree.is_symlink()
            or not worktree.is_dir() or not destination.is_absolute()
            or destination.is_symlink() or destination.exists()):
        raise PawWorktreeBoundaryError("paw_bundle_paths_invalid")
    ref = BRANCH_PREFIX + work_id
    def git(*args):
        try:
            return subprocess.run(
                ["git", "-C", str(worktree), *args], check=True,
                capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise PawWorktreeBoundaryError("paw_bundle_export_failed") from exc
    if git("symbolic-ref", "--quiet", "--short", "HEAD") != ref:
        raise PawWorktreeBoundaryError("paw_bundle_branch_mismatch")
    if git("rev-parse", "HEAD") != commit_sha or git("status", "--porcelain"):
        raise PawWorktreeBoundaryError("paw_bundle_source_mismatch")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    git("bundle", "create", str(destination), "refs/heads/" + ref)
    if not destination.is_file() or destination.is_symlink():
        raise PawWorktreeBoundaryError("paw_bundle_export_failed")
    return destination
