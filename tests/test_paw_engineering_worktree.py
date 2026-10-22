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


def test_prepare_then_apply_candidate_without_touching_base(tmp_path):
    """Exercise the actual two stages together; never mark Claw acceptance."""
    import hashlib
    from agentos_node.paw_engineering_candidate import apply_bounded_test_candidate

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    source = repo / "tests/test_paw_engineering_worktree.py"
    source.parent.mkdir()
    source.write_text("def test_one():\n    assert True\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD")
    workspace = tmp_path / "isolated"
    workspace.mkdir()
    prepared = prepare_paw_worktree(
        repository=repo, workspace_root=workspace, work_id="a", base_sha=base_sha,
    )
    target = prepared.path / "tests/test_paw_engineering_worktree.py"
    receipt = apply_bounded_test_candidate(
        prepared, relative_path="tests/test_paw_engineering_worktree.py",
        expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        replacement="def test_one():\n    assert True\n\ndef test_two():\n    assert 2 + 2 == 4\n",
    )
    assert receipt.test_pass is True
    assert receipt.independent_acceptance_pass is False
    assert receipt.branch == "paw/470/a"
    assert receipt.base_sha == base_sha
    assert receipt.content_sha256 == hashlib.sha256(target.read_bytes()).hexdigest()
    assert source.read_text() == "def test_one():\n    assert True\n"
    assert git(repo, "rev-parse", "HEAD") == base_sha
    assert git(repo, "status", "--porcelain") == ""
