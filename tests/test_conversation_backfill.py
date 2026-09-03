from __future__ import annotations

import json
from pathlib import Path

from agentos_node.conversation_backfill import backfill_conversation_candidates
from agentos_node.client_cli import build_parser


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_backfill_creates_reviewable_candidates_without_raw_transcript(tmp_path: Path):
    root = tmp_path / "projects"
    conversation = root / "alpha" / "logs" / "conversations" / "conv-1"
    _write(conversation / "walkthrough.md", "# Delivery\n\nStatus: Completed\n\nRegression: PASS\n")
    _write(conversation / "browser" / "scratchpad.md", "secret raw browser content must not be read")

    report = backfill_conversation_candidates(projects_root=root, candidate_root=tmp_path / "candidates", max_conversations=10)

    assert report["created_candidates"] == 1
    assert report["before_candidate_count"] == 0
    assert report["after_candidate_count"] == 1
    assert report["raw_conversation_copied"] is False
    candidate_path = next((tmp_path / "candidates").rglob("*.json"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["status"] == "candidate"
    assert candidate["promotion_required"] is True
    assert candidate["source_files"] == ["walkthrough.md"]
    assert "secret" not in json.dumps(candidate)


def test_backfill_is_idempotent_and_ignores_non_terminal_conversations(tmp_path: Path):
    root = tmp_path / "projects"
    completed = root / "alpha" / "logs" / "conversations" / "done"
    pending = root / "alpha" / "logs" / "conversations" / "pending"
    _write(completed / "task.md", "- [x] Completed\n")
    _write(pending / "implementation_plan.md", "- [ ] Still researching\n")

    first = backfill_conversation_candidates(projects_root=root, candidate_root=tmp_path / "candidates", max_conversations=10)
    second = backfill_conversation_candidates(projects_root=root, candidate_root=tmp_path / "candidates", max_conversations=10)

    assert first["created_candidates"] == 1
    assert first["candidate_count"] == 1
    assert first["before_candidate_count"] == 0
    assert first["after_candidate_count"] == 1
    assert second["created_candidates"] == 0
    assert second["existing_candidates"] == 1
    assert second["before_candidate_count"] == 1
    assert second["after_candidate_count"] == 1


def test_backfill_is_bounded(tmp_path: Path):
    root = tmp_path / "projects"
    for index in range(3):
        _write(root / "alpha" / "logs" / "conversations" / f"c{index}" / "walkthrough.md", "PASS\n")

    report = backfill_conversation_candidates(projects_root=root, candidate_root=tmp_path / "candidates", max_conversations=2)

    assert report["scanned_conversations"] == 2
    assert report["candidate_count"] == 2


def test_node_join_exposes_opt_in_historical_backfill_arguments():
    args = build_parser().parse_args(
        [
            "join",
            "--one",
            "https://one.example",
            "--historical-projects-root",
            "/history/projects",
            "--historical-candidate-root",
            "/history/candidates",
            "--historical-max-conversations",
            "25",
        ]
    )
    assert args.historical_projects_root == Path("/history/projects")
    assert args.historical_candidate_root == Path("/history/candidates")
    assert args.historical_max_conversations == 25
