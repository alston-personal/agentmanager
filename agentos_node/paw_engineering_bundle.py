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
            or not destination.is_absolute() or destination.exists() or destination.is_symlink()):
        raise PawWorktreeBoundaryError("paw_bundle_paths_invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
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
    git("init", "--bare", "-q")
    ref = BRANCH_PREFIX + work_id
    git("bundle", "verify", str(bundle))
    git("fetch", "--no-tags", str(bundle), "refs/heads/" + ref + ":refs/heads/" + ref)
    actual = git("rev-parse", "refs/heads/" + ref)
    if actual != commit_sha:
        raise PawWorktreeBoundaryError("paw_bundle_head_mismatch")
    return destination
