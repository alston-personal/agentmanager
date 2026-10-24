import json

import pytest

from agentos_node.paw_engineering_handoff_publisher import publish_durable_paw_handoff
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def test_durable_handoff_publisher_reads_real_receipt_and_delegates(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    directory = runtime / "lifecycle/receipts/paw-470-inspection-v1"
    directory.mkdir(parents=True)
    worktrees = tmp_path / "worktrees"
    (worktrees / "issue-470-a").mkdir(parents=True)
    receipt = {
        "schema": "agentos.employee-assignment-receipt/v1",
        "employee_id": "the-paw", "assignment_id": "paw-470-inspection-v1",
        "generation": 1, "outcome": "handoff", "credential_exposed": False,
        "thread_head": "paw:local-commit:" + "b" * 40,
        "result_summary": {
            "bounded_stage": "paw-authorized-local-commit",
            "work_id": "issue-470-a", "base_sha": "a" * 40,
            "commit_sha": "b" * 40, "branch": "paw/470/issue-470-a",
            "changed_file": "tests/test_paw_engineering_worktree.py",
            "published": False, "independent_acceptance_pass": False,
            "mutation_performed": True,
        },
    }
    target = directory / "000001.json"
    target.write_text(json.dumps(receipt))
    import agentos_node.paw_engineering_handoff_publisher as module
    seen = []
    def publisher(local, *, worktree, authenticated_publisher):
        seen.append((local, worktree, authenticated_publisher))
        return "draft-pr-receipt"
    monkeypatch.setattr(module, "publish_with_trusted_gh", publisher)
    assert publish_durable_paw_handoff(
        runtime_root=runtime, workspace_root=worktrees,
        generation=1, authenticated_publisher=True,
    ) == "draft-pr-receipt"
    assert len(seen) == 1
    assert seen[0][0].commit_sha == "b" * 40
    assert seen[0][1] == worktrees / "issue-470-a"
    assert seen[0][2] is True

    receipt["result_summary"]["published"] = True
    target.write_text(json.dumps(receipt))
    with pytest.raises(PawWorktreeBoundaryError, match="evidence_invalid"):
        publish_durable_paw_handoff(
            runtime_root=runtime, workspace_root=worktrees,
            generation=1, authenticated_publisher=True,
        )
    assert len(seen) == 1


def test_durable_handoff_publisher_does_not_read_without_authority(tmp_path):
    with pytest.raises(PawWorktreeBoundaryError, match="not_authorized"):
        publish_durable_paw_handoff(
            runtime_root=tmp_path, workspace_root=tmp_path,
            generation=1, authenticated_publisher=False,
        )
