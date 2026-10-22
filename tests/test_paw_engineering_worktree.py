from __future__ import annotations

import subprocess
import pytest

from agentos_node.paw_engineering_worktree import (
    PawWorktreeBoundaryError, prepare_paw_worktree,
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True,
    ).stdout.strip()


def initialized(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    (repo / "file.txt").write_text("base\n")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def test_prepares_only_isolated_branch_and_does_not_mutate_base(tmp_path):
    repo, sha = initialized(tmp_path)
    root = tmp_path / "paw-workspaces"
    root.mkdir()
    result = prepare_paw_worktree(
        repository=repo, workspace_root=root, work_id="issue-470-a", base_sha=sha,
    )
    assert result.branch == "paw/470/issue-470-a"
    assert result.base_sha == sha
    assert result.mutation_performed is False
    assert result.independent_acceptance_pass is False
    assert git(result.path, "rev-parse", "HEAD") == sha
    assert git(repo, "rev-parse", "HEAD") == sha
    with pytest.raises(PawWorktreeBoundaryError, match="requires_reconciliation"):
        prepare_paw_worktree(
            repository=repo, workspace_root=root, work_id="issue-470-a", base_sha=sha,
        )


@pytest.mark.parametrize("work_id", [
    "../main", "MAIN", "foo/bar", "branch;touch", ".hidden", "",
])
def test_denies_untrusted_work_ids(tmp_path, work_id):
    repo, sha = initialized(tmp_path)
    root = tmp_path / "isolated"
    root.mkdir()
    with pytest.raises(PawWorktreeBoundaryError):
        prepare_paw_worktree(repository=repo, workspace_root=root, work_id=work_id, base_sha=sha)


def test_denies_wrong_repo_stale_sha_and_dirty_checkout(tmp_path):
    repo, sha = initialized(tmp_path)
    root = tmp_path / "isolated"
    root.mkdir()
    with pytest.raises(PawWorktreeBoundaryError, match="not_authorized"):
        prepare_paw_worktree(repository=repo, workspace_root=root, work_id="safe", base_sha=sha, repository_id="other/repo")
    with pytest.raises(PawWorktreeBoundaryError, match="base_commit_invalid"):
        prepare_paw_worktree(repository=repo, workspace_root=root, work_id="safe", base_sha="main")
    (repo / "file.txt").write_text("dirty\n")
    with pytest.raises(PawWorktreeBoundaryError, match="repository_dirty"):
        prepare_paw_worktree(repository=repo, workspace_root=root, work_id="safe", base_sha=sha)


def test_denies_workspace_inside_checkout(tmp_path):
    repo, sha = initialized(tmp_path)
    root = repo / "work"
    root.mkdir()
    with pytest.raises(PawWorktreeBoundaryError, match="not_isolated"):
        prepare_paw_worktree(repository=repo, workspace_root=root, work_id="safe", base_sha=sha)
