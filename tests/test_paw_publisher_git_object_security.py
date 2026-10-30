"""Behavioral security regression: inspect actual Git objects before any GH network call."""
import subprocess
from dataclasses import replace

import pytest

from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
from agentos_node.paw_engineering_gh_transport import publish_with_trusted_gh
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError
import agentos_node.paw_engineering_gh_transport as transport


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def make_case(tmp_path, extra=False):
    source = tmp_path / "worker"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "Paw")
    git(source, "config", "user.email", "paw@example.invalid")
    allowed = source / "tests" / "test_paw_engineering_worktree.py"
    allowed.parent.mkdir()
    allowed.write_text("initial\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "base")
    base = git(source, "rev-parse", "HEAD")
    branch = "paw/470/issue-470-a"
    git(source, "checkout", "-qb", branch)
    allowed.write_text("candidate\n")
    if extra:
        (source / "unexpected.txt").write_text("unauthorized\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "candidate")
    head = git(source, "rev-parse", "HEAD")
    bare = tmp_path / "publisher.git"
    git(source, "clone", "--bare", "-q", str(source), str(bare))
    receipt = PawLocalCommitReceipt(
        schema="agentos.paw-local-commit-receipt/v1", work_id="issue-470-a",
        base_sha=base, commit_sha=head, branch=branch,
        changed_file="tests/test_paw_engineering_worktree.py",
    )
    return bare, receipt


def test_real_bare_git_objects_allow_only_exact_one_file(tmp_path, monkeypatch):
    repo, receipt = make_case(tmp_path)
    monkeypatch.setattr(transport, "publish_paw_draft", lambda *a, **k: "admitted")
    assert publish_with_trusted_gh(receipt, worktree=repo, authenticated_publisher=True,
                                  bare_repository=True) == "admitted"


def test_real_bare_git_objects_reject_wrong_parent_before_network(tmp_path, monkeypatch):
    repo, receipt = make_case(tmp_path)
    monkeypatch.setattr(transport, "publish_paw_draft",
                        lambda *a, **k: pytest.fail("network stage reached"))
    with pytest.raises(PawWorktreeBoundaryError, match="parent_mismatch"):
        publish_with_trusted_gh(replace(receipt, base_sha="a" * 40), worktree=repo,
                                authenticated_publisher=True, bare_repository=True)


def test_real_bare_git_objects_reject_extra_file_before_network(tmp_path, monkeypatch):
    repo, receipt = make_case(tmp_path, extra=True)
    monkeypatch.setattr(transport, "publish_paw_draft",
                        lambda *a, **k: pytest.fail("network stage reached"))
    with pytest.raises(PawWorktreeBoundaryError, match="object_scope_invalid"):
        publish_with_trusted_gh(receipt, worktree=repo, authenticated_publisher=True,
                                bare_repository=True)
