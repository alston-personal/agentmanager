"""Trusted Paw publisher handoff boundary; never invoked by the wake worker.

Consumes the existing immutable EmployeeLifecycle terminal receipt, checks
provenance against the isolated Git worktree, and delegates only a draft PR.
The caller must independently authenticate its GitHub publishing identity.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentos_node.paw_engineering_commit import PawLocalCommitReceipt
from agentos_node.paw_engineering_gh_transport import publish_with_trusted_gh
from agentos_node.paw_engineering_worktree import BRANCH_PREFIX, PawWorktreeBoundaryError, _ID, _SHA

ASSIGNMENT = "paw-470-inspection-v1"


def publish_durable_paw_handoff(
    *, runtime_root: Path, workspace_root: Path, generation: int,
    authenticated_publisher: bool, publication_root: Path | None = None,
    assignment_id: str = ASSIGNMENT,
):
    if not authenticated_publisher:
        raise PawWorktreeBoundaryError("paw_handoff_publisher_not_authorized")
    if type(generation) is not int or generation < 1:
        raise PawWorktreeBoundaryError("paw_handoff_generation_invalid")
    if assignment_id != ASSIGNMENT:
        # A future Paw B must be a uniquely bound, governed WorkItem. Never
        # discover new publishing authority from a receipt file alone.
        from agent_core.employee_runtime import EmployeeRuntime
        from agentos_node.paw_engineering_grant import require_dynamic_paw_assignment_binding
        if not isinstance(assignment_id, str) or not _ID.fullmatch(assignment_id):
            raise PawWorktreeBoundaryError("paw_handoff_assignment_invalid")
        require_dynamic_paw_assignment_binding(
            assignment_id=assignment_id, runtime=EmployeeRuntime(runtime_root),
        )
    receipt_path = (
        Path(runtime_root) / "lifecycle" / "receipts" /
        assignment_id / f"{generation:06d}.json"
    )
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise PawWorktreeBoundaryError("paw_handoff_receipt_missing")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise PawWorktreeBoundaryError("paw_handoff_receipt_invalid") from exc
    if not isinstance(receipt, dict) or (
        receipt.get("schema") != "agentos.employee-assignment-receipt/v1"
        or receipt.get("assignment_id") != assignment_id
        or receipt.get("employee_id") != "the-paw"
        or receipt.get("generation") != generation
        or receipt.get("outcome") != "handoff"
        or receipt.get("credential_exposed") is not False
    ):
        raise PawWorktreeBoundaryError("paw_handoff_receipt_invalid")
    summary = receipt.get("result_summary")
    if not isinstance(summary, dict) or (
        summary.get("bounded_stage") != "paw-authorized-local-commit"
        or summary.get("published") is not False
        or summary.get("independent_acceptance_pass") is not False
        or summary.get("mutation_performed") is not True
    ):
        raise PawWorktreeBoundaryError("paw_handoff_evidence_invalid")
    work_id = summary.get("work_id")
    base = summary.get("base_sha")
    head = summary.get("commit_sha")
    branch = summary.get("branch")
    if (
        not isinstance(work_id, str) or not _ID.fullmatch(work_id)
        or not isinstance(base, str) or not _SHA.fullmatch(base)
        or not isinstance(head, str) or not _SHA.fullmatch(head)
        or branch != BRANCH_PREFIX + work_id
        or summary.get("changed_file") != "tests/test_paw_engineering_worktree.py"
        or receipt.get("thread_head") != "paw:local-commit:" + head
    ):
        raise PawWorktreeBoundaryError("paw_handoff_provenance_invalid")
    if publication_root is None or not Path(publication_root).is_absolute():
        raise PawWorktreeBoundaryError("paw_bundle_publication_root_required")
    bundle = summary.get("bundle_path")
    expected = Path(workspace_root).parent / "paw-470-bundles" / (work_id + ".bundle")
    if not isinstance(bundle, str) or bundle != str(expected):
        raise PawWorktreeBoundaryError("paw_bundle_handoff_path_invalid")
    from agentos_node.paw_engineering_bundle import import_paw_bundle
    local = PawLocalCommitReceipt(
        schema="agentos.paw-local-commit-receipt/v1",
        work_id=work_id, base_sha=base, commit_sha=head,
        branch=branch, changed_file=summary["changed_file"],
    )
    destination = Path(publication_root) / "repositories" / (work_id + ".git")
    repository = import_paw_bundle(
        bundle=expected, destination=destination,
        work_id=work_id, commit_sha=head,
    )
    return publish_with_trusted_gh(
        local, worktree=repository, authenticated_publisher=True,
        bare_repository=True,
    )
