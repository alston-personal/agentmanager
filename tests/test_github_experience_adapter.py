from agent_core.source_adapters.base import SourceCursor
from agent_core.source_adapters.github import (
    GitHubExperienceAdapter,
    GitHubRecord,
    record_from_commit_snapshot,
    record_from_pr_snapshot,
    record_from_workflow_summary,
)


def test_pr_snapshot_becomes_bounded_record():
    record = record_from_pr_snapshot(
        {
            "number": 3,
            "title": "State Kernel v2 foundation",
            "body": "Experimental cognitive work",
            "state": "open",
            "draft": True,
            "merged": False,
            "mergeable": True,
            "head": "feature/state-kernel-v2",
            "head_sha": "abc123",
            "updated_at": "2026-08-21T12:00:00Z",
            "url": "https://github.com/example/repo/pull/3",
            "user": {"login": "alstonhuang"},
            "unrelated_large_payload": {"ignored": True},
        }
    )
    assert record.kind == "pull_request"
    assert record.id == "3"
    assert record.actor == "alstonhuang"
    assert "State Kernel v2 foundation" in record.content
    assert record.metadata["head_sha"] == "abc123"
    assert "unrelated_large_payload" not in record.metadata


def test_commit_snapshot_becomes_bounded_record():
    record = record_from_commit_snapshot(
        {
            "commit": {"sha": "abcdef1234567890", "message": "feat: cognitive kernel"},
            "created_at": "2026-08-21T12:00:00Z",
            "author": {"login": "alstonhuang"},
            "html_url": "https://github.com/example/repo/commit/abcdef",
            "diff": "must not be copied wholesale",
        }
    )
    assert record.kind == "commit"
    assert record.id == "abcdef1234567890"
    assert "feat: cognitive kernel" in record.content
    assert "must not be copied" not in record.content


def test_workflow_summary_never_includes_logs():
    record = record_from_workflow_summary(
        {
            "id": 99,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "updated_at": "2026-08-21T12:00:00Z",
            "run_number": 12,
            "head_sha": "abc",
            "logs": "SECRET OR HUGE LOG",
        }
    )
    assert record.kind == "workflow_run"
    assert "success" in record.content
    assert "SECRET" not in record.content
    assert "logs" not in record.metadata


def test_adapter_is_idempotent_and_strips_credential_metadata():
    records = [
        GitHubRecord(
            kind="issue_comment",
            id="1001",
            occurred_at="2026-08-21T12:00:00Z",
            actor="reviewer",
            content="Consider preserving provenance.",
            conversation_ref="github:pr:3",
            metadata={
                "token": "never-store-me",
                "authorization": "Bearer never",
                "raw_logs": "huge",
                "comment_type": "review",
            },
        )
    ]

    def fetcher(position, limit):
        assert position is None
        assert limit == 50
        return records, None

    adapter = GitHubExperienceAdapter("alston-personal/agentmanager", fetcher)
    first = adapter.fetch_page("agentmanager")
    second = adapter.fetch_page("agentmanager")
    assert first.batch.event_ids == second.batch.event_ids
    event = first.batch.events[0]
    assert event.source_ref == "github:alston-personal/agentmanager:issue_comment:1001"
    assert event.metadata["comment_type"] == "review"
    assert "token" not in event.metadata
    assert "authorization" not in event.metadata
    assert "raw_logs" not in event.metadata


def test_cursor_and_bounded_page_contract():
    pages = {
        None: ([GitHubRecord("commit", "a", "2026-08-21T10:00:00Z", "a", "first")], "page2"),
        "page2": ([GitHubRecord("commit", "b", "2026-08-21T11:00:00Z", "a", "second")], None),
    }

    def fetcher(position, limit):
        return pages[position]

    adapter = GitHubExperienceAdapter("o/r", fetcher)
    first = adapter.fetch_page("p", limit=1)
    assert first.has_more is True
    assert first.next_cursor == SourceCursor("github", "page2")
    second = adapter.fetch_page("p", first.next_cursor, limit=1)
    assert second.has_more is False
    assert second.next_cursor is None
    assert first.batch.event_ids != second.batch.event_ids


def test_wrong_cursor_source_and_oversized_fetch_fail_closed():
    def fetcher(position, limit):
        return [
            GitHubRecord("commit", "a", "2026-08-21T10:00:00Z", "a", "first"),
            GitHubRecord("commit", "b", "2026-08-21T11:00:00Z", "a", "second"),
        ], None

    adapter = GitHubExperienceAdapter("o/r", fetcher)
    try:
        adapter.fetch_page("p", SourceCursor("other", "x"))
    except ValueError as exc:
        assert "source_kind" in str(exc)
    else:
        raise AssertionError("expected wrong source cursor rejection")

    try:
        adapter.fetch_page("p", limit=1)
    except ValueError as exc:
        assert "more records" in str(exc)
    else:
        raise AssertionError("expected oversized page rejection")
