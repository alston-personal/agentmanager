"""Narrow PR publication boundary for an already verified Paw local commit.

Only a separately authenticated publisher may supply the remote transport.
Never merge, deploy, mark DONE or claim independent Claw acceptance here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
from agentos_node.paw_engineering_worktree import (
    BRANCH_PREFIX, PawWorktreeBoundaryError, _ID, _SHA,
)

BASE = "core/integration"
REPO = "alston-personal/agentmanager"


@dataclass(frozen=True)
class PawPublicationReceipt:
    schema: str
    work_id: str
    commit_sha: str
    branch: str
    pr_number: int
    pr_url: str
    published: bool = True
    merged: bool = False
    independent_acceptance_pass: bool = False


def publish_paw_draft(
    local: PawLocalCommitReceipt, *,
    lookup_pr: Callable[[str, str], Mapping[str, object] | None],
    publish_branch: Callable[[str, str], None],
    create_draft_pr: Callable[[str, str, str], Mapping[str, object]],
    authenticated_publisher: bool,
) -> PawPublicationReceipt:
    """Publish exact commit on fixed branch and reuse an existing matching PR.

    Callbacks must be a trusted authenticated transport, not wake/model input.
    An existing PR is returned only when its exact head commit matches.
    """
    if not authenticated_publisher:
        raise PawWorktreeBoundaryError("paw_publisher_not_authorized")
    if (
        local.schema != "agentos.paw-local-commit-receipt/v1"
        or not _ID.fullmatch(local.work_id)
        or local.branch != BRANCH_PREFIX + local.work_id
        or not _SHA.fullmatch(local.commit_sha)
        or not _SHA.fullmatch(local.base_sha)
        or local.published or local.independent_acceptance_pass
        or local.changed_file != "tests/test_paw_engineering_worktree.py"
    ):
        raise PawWorktreeBoundaryError("paw_publication_scope_invalid")

    def check_pr(pr: Mapping[str, object]) -> PawPublicationReceipt:
        if (
            pr.get("head") != local.branch
            or pr.get("head_sha") != local.commit_sha
            or pr.get("base") != BASE
            or pr.get("repo") != REPO
            or pr.get("draft") is not True
            or pr.get("merged") is not False
            or type(pr.get("number")) is not int
            or pr["number"] < 1
            or not isinstance(pr.get("url"), str)
            or not pr["url"].startswith("https://github.com/" + REPO + "/pull/")
        ):
            raise PawWorktreeBoundaryError("paw_publication_remote_receipt_invalid")
        return PawPublicationReceipt(
            "agentos.paw-draft-publication-receipt/v1", local.work_id,
            local.commit_sha, local.branch, pr["number"], pr["url"],
        )

    existing = lookup_pr(REPO, local.branch)
    if existing is not None:
        return check_pr(existing)
    publish_branch(local.branch, local.commit_sha)
    return check_pr(create_draft_pr(REPO, local.branch, BASE))
