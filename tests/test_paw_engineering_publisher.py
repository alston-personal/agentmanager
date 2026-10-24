from dataclasses import replace

import pytest

from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
from agentos_node.paw_engineering_publisher import publish_paw_draft
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def local():
    return PawLocalCommitReceipt(
        schema="agentos.paw-local-commit-receipt/v1",
        work_id="issue-470-a", base_sha="a" * 40,
        commit_sha="b" * 40, branch="paw/470/issue-470-a",
        changed_file="tests/test_paw_engineering_worktree.py",
    )


def test_publish_draft_once_and_reuse_matching_pr():
    seen = {"branch": 0, "create": 0}
    state = {"pr": None}

    def lookup(repo, branch):
        return state["pr"]

    def branch(name, sha):
        seen["branch"] += 1
        assert name == local().branch and sha == local().commit_sha

    def create(repo, head, base):
        seen["create"] += 1
        assert base == "core/integration"
        state["pr"] = {
            "repo": repo, "head": head, "base": base,
            "head_sha": local().commit_sha,
            "draft": True, "merged": False, "number": 2099,
            "url": "https://github.com/alston-personal/agentmanager/pull/2099",
        }
        return state["pr"]

    for _ in range(2):
        receipt = publish_paw_draft(
            local(), lookup_pr=lookup,
            publish_branch=branch, create_draft_pr=create,
            authenticated_publisher=True,
        )
        assert receipt.published and not receipt.merged
        assert not receipt.independent_acceptance_pass
    assert seen == {"branch": 1, "create": 1}


def test_publisher_rejects_absent_authority_or_unverified_scope():
    def forbid(*args):
        raise AssertionError("remote transport must not be invoked")

    with pytest.raises(PawWorktreeBoundaryError, match="not_authorized"):
        publish_paw_draft(
            local(), lookup_pr=forbid, publish_branch=forbid,
            create_draft_pr=forbid, authenticated_publisher=False,
        )
    with pytest.raises(PawWorktreeBoundaryError, match="scope_invalid"):
        publish_paw_draft(
            replace(local(), branch="main"),
            lookup_pr=forbid, publish_branch=forbid,
            create_draft_pr=forbid, authenticated_publisher=True,
        )


def test_existing_wrong_head_fails_closed_without_duplication():
    def existing(repo, branch):
        return {
            "repo": repo, "head": branch, "head_sha": "c" * 40,
            "base": "core/integration", "draft": True,
            "merged": False, "number": 2099,
            "url": "https://github.com/alston-personal/agentmanager/pull/2099",
        }

    def forbid(*args):
        raise AssertionError("must reconcile existing PR rather than write")

    with pytest.raises(PawWorktreeBoundaryError, match="remote_receipt_invalid"):
        publish_paw_draft(
            local(), lookup_pr=existing, publish_branch=forbid,
            create_draft_pr=forbid, authenticated_publisher=True,
        )


def test_remote_pr_created_then_local_receipt_write_crashes_retry_reuses_pr():
    """A crash after GitHub creation must not create a second remote PR."""
    remote = {"pr": None, "push_count": 0, "create_count": 0}

    def lookup(repo, branch):
        return remote["pr"]

    def push(branch, sha):
        remote["push_count"] += 1

    def create(repo, head, base):
        remote["create_count"] += 1
        remote["pr"] = {
            "repo": repo, "head": head, "base": base,
            "head_sha": local().commit_sha, "draft": True,
            "merged": False, "number": 2099,
            "url": "https://github.com/alston-personal/agentmanager/pull/2099",
        }
        return remote["pr"]

    first = publish_paw_draft(
        local(), lookup_pr=lookup, publish_branch=push,
        create_draft_pr=create, authenticated_publisher=True,
    )
    assert first.pr_number == 2099
    # Simulate a process crash before the caller persisted the publication receipt.
    recovered = publish_paw_draft(
        local(), lookup_pr=lookup, publish_branch=push,
        create_draft_pr=create, authenticated_publisher=True,
    )
    assert recovered == first
    assert remote["push_count"] == 1
    assert remote["create_count"] == 1


def test_crashed_publish_recovery_rejects_changed_remote_head():
    remote = {
        "repo": "alston-personal/agentmanager",
        "head": local().branch,
        "base": "core/integration",
        "head_sha": "c" * 40,
        "draft": True, "merged": False,
        "number": 2099,
        "url": "https://github.com/alston-personal/agentmanager/pull/2099",
    }

    def forbidden(*args):
        raise AssertionError("remote mutation forbidden on head mismatch")

    with pytest.raises(PawWorktreeBoundaryError, match="remote_receipt_invalid"):
        publish_paw_draft(
            local(), lookup_pr=lambda *args: remote,
            publish_branch=forbidden, create_draft_pr=forbidden,
            authenticated_publisher=True,
        )
