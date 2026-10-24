from pathlib import Path
from types import SimpleNamespace

import pytest

import agentos_node.paw_engineering_publisher_cli as cli
from agentos_node.paw_engineering_worktree import PawWorktreeBoundaryError


def test_publisher_cli_denies_absent_identity_before_transport(tmp_path, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("publisher invoked without identity")
    monkeypatch.setattr(cli, "publish_durable_paw_handoff", forbidden)
    with pytest.raises(PawWorktreeBoundaryError, match="identity_missing"):
        cli.publish_once(
            runtime_root=tmp_path / "runtime",
            workspace_root=tmp_path / "worktrees",
            generation=1, environment={},
        )


def test_publisher_cli_reports_external_draft_without_false_acceptance(tmp_path, monkeypatch):
    captured = []
    def publisher(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            schema="agentos.paw-draft-publication-receipt/v1",
            work_id="issue-470-a", commit_sha="b" * 40,
            pr_number=2099,
            pr_url="https://github.com/alston-personal/agentmanager/pull/2099",
        )
    monkeypatch.setattr(cli, "publish_durable_paw_handoff", publisher)
    result = cli.publish_once(
        runtime_root=tmp_path / "runtime",
        workspace_root=tmp_path / "worktrees",
        generation=1, environment={"GH_TOKEN": "test-only"},
    )
    assert len(captured) == 1
    assert captured[0]["authenticated_publisher"] is True
    assert result["status"] == "published_draft"
    assert result["merged"] is False
    assert result["independent_acceptance_pass"] is False


def test_publisher_cli_requires_absolute_roots(tmp_path):
    with pytest.raises(PawWorktreeBoundaryError, match="absolute_roots_required"):
        cli.publish_once(
            runtime_root=Path("relative"), workspace_root=tmp_path,
            generation=1, environment={"GH_TOKEN": "test-only"},
        )

def test_latest_publisher_idle_without_terminal_receipt(tmp_path):
    assert cli.publish_latest(runtime_root=tmp_path, workspace_root=tmp_path)["status"] == "idle"

def test_latest_publisher_uses_highest_generation(tmp_path, monkeypatch):
    directory = tmp_path / "lifecycle/receipts/paw-470-inspection-v1"
    directory.mkdir(parents=True)
    for name in ("000002.json", "000010.json", "invalid.json"):
        (directory / name).write_text("{}")
    generations = []
    def publish(**kwargs):
        generations.append(kwargs["generation"])
        return {"status": "published_draft"}
    monkeypatch.setattr(cli, "publish_once", publish)
    result = cli.publish_latest(runtime_root=tmp_path, workspace_root=tmp_path)
    assert result["status"] == "published_draft"
    assert generations == [10]
