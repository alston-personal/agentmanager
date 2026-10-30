import subprocess

import pytest

from agentos_node.paw_engineering_bundle import import_paw_bundle
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def test_bundle_import_into_publisher_owned_bare_repo(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    git(worker, "init", "-q")
    git(worker, "config", "user.name", "Paw Test")
    git(worker, "config", "user.email", "paw@example.invalid")
    (worker / "candidate.txt").write_text("bounded\n")
    git(worker, "add", "candidate.txt")
    git(worker, "commit", "-qm", "candidate")
    branch = "paw/470/issue-470-a"
    git(worker, "branch", branch)
    head = git(worker, "rev-parse", "HEAD")
    bundle = tmp_path / "candidate.bundle"
    git(worker, "bundle", "create", str(bundle), branch)
    target = tmp_path / "publisher" / "repo.git"
    result = import_paw_bundle(
        bundle=bundle, destination=target, work_id="issue-470-a",
        commit_sha=head,
    )
    assert result == target
    assert git(target, "rev-parse", "refs/heads/" + branch) == head
    assert import_paw_bundle(bundle=bundle, destination=target,
                             work_id="issue-470-a", commit_sha=head) == target
    with pytest.raises(PawWorktreeBoundaryError, match="existing_head_mismatch"):
        import_paw_bundle(bundle=bundle, destination=target,
                          work_id="issue-470-a", commit_sha="a" * 40)


def test_bundle_import_rejects_wrong_commit(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    git(worker, "init", "-q")
    git(worker, "config", "user.name", "Paw Test")
    git(worker, "config", "user.email", "paw@example.invalid")
    (worker / "candidate.txt").write_text("bounded\n")
    git(worker, "add", "candidate.txt")
    git(worker, "commit", "-qm", "candidate")
    branch = "paw/470/issue-470-a"
    git(worker, "branch", branch)
    bundle = tmp_path / "candidate.bundle"
    git(worker, "bundle", "create", str(bundle), branch)
    with pytest.raises(PawWorktreeBoundaryError, match="head_mismatch"):
        import_paw_bundle(bundle=bundle, destination=tmp_path / "separate.git",
                          work_id="issue-470-a", commit_sha="a" * 40)


def test_resume_bare_repository_after_init_before_fetch(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    git(worker, "init", "-q")
    git(worker, "config", "user.name", "Paw Test")
    git(worker, "config", "user.email", "paw@example.invalid")
    (worker / "candidate.txt").write_text("recovery\n")
    git(worker, "add", "candidate.txt")
    git(worker, "commit", "-qm", "candidate")
    branch = "paw/470/issue-470-a"
    git(worker, "branch", branch)
    head = git(worker, "rev-parse", "HEAD")
    bundle = tmp_path / "candidate.bundle"
    git(worker, "bundle", "create", str(bundle), branch)
    target = tmp_path / "publisher/repo.git"
    target.mkdir(parents=True)
    git(target, "init", "--bare", "-q")
    assert import_paw_bundle(bundle=bundle, destination=target,
                             work_id="issue-470-a", commit_sha=head) == target
    assert git(target, "rev-parse", "refs/heads/" + branch) == head
