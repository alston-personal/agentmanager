"""GitHub -> ExperienceEvent normalization for shadow Cognitive ingestion.

The adapter accepts a fetcher callable so GitHub connector/REST/gh implementations
remain outside Cognitive Kernel semantics. It is read-only and intentionally
stores no credentials, raw authorization headers, or full CI logs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Iterable, Mapping, Sequence

from agent_core.source_adapters.base import SourceCursor, SourcePage
from runtime_core.experience_ir import ExperienceBatch, ExperienceEvent


GITHUB_SOURCE_KIND = "github"
_ALLOWED_KINDS = {"pull_request", "issue_comment", "review", "commit", "workflow_run"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_metadata(value: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in keys:
        item = value.get(key)
        if item is not None and item != "":
            result[key] = item
    return result


@dataclass(frozen=True)
class GitHubRecord:
    kind: str
    id: str
    occurred_at: str
    actor: str
    content: str
    url: str | None = None
    conversation_ref: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported GitHub record kind: {self.kind}")
        for name in ("id", "occurred_at", "actor", "content"):
            if not _text(getattr(self, name)):
                raise ValueError(f"GitHub record {name} is required")


class GitHubExperienceAdapter:
    """Normalize bounded GitHub records into source-neutral ExperienceEvents."""

    source_kind = GITHUB_SOURCE_KIND

    def __init__(
        self,
        repository: str,
        fetcher: Callable[[str | None, int], tuple[Sequence[GitHubRecord], str | None]],
    ) -> None:
        repository = _text(repository)
        if "/" not in repository:
            raise ValueError("repository must be owner/name")
        self.repository = repository
        self.fetcher = fetcher

    def _event(self, project_id: str, record: GitHubRecord) -> ExperienceEvent:
        source_ref = f"github:{self.repository}:{record.kind}:{record.id}"
        metadata = {
            "repository": self.repository,
            "github_kind": record.kind,
            **dict(record.metadata or {}),
        }
        if record.url:
            metadata["url"] = record.url
        # Explicitly discard common credential/log payload keys if a caller
        # accidentally included them in metadata.
        for forbidden in (
            "token",
            "authorization",
            "authorization_header",
            "cookie",
            "secret",
            "raw_logs",
            "logs",
        ):
            metadata.pop(forbidden, None)

        return ExperienceEvent(
            project_id=project_id,
            source_kind=GITHUB_SOURCE_KIND,
            source_ref=source_ref,
            actor_kind="human_or_automation",
            event_kind=record.kind,
            content=record.content,
            occurred_at=record.occurred_at,
            trust_class="observed",
            conversation_ref=record.conversation_ref,
            metadata=metadata,
        )

    def fetch_page(
        self,
        project_id: str,
        cursor: SourceCursor | None = None,
        *,
        limit: int = 50,
    ) -> SourcePage:
        if not _text(project_id):
            raise ValueError("project_id is required")
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        if cursor is not None and cursor.source_kind != self.source_kind:
            raise ValueError("cursor source_kind does not match GitHub adapter")
        position = cursor.position if cursor else None
        records, next_position = self.fetcher(position, limit)
        if len(records) > limit:
            raise ValueError("GitHub fetcher returned more records than requested limit")
        events = tuple(self._event(project_id, item) for item in records)
        window = f"github:{self.repository}:{position or 'start'}:{next_position or 'end'}"
        batch = ExperienceBatch(
            project_id=project_id,
            events=events,
            source_window_ref=window,
        )
        next_cursor = (
            SourceCursor(self.source_kind, next_position) if next_position is not None else None
        )
        return SourcePage(batch=batch, next_cursor=next_cursor, has_more=next_cursor is not None)


def record_from_pr_snapshot(snapshot: Mapping[str, Any]) -> GitHubRecord:
    """Normalize a GitHub PR snapshot without embedding its entire API payload."""
    number = snapshot.get("number")
    title = _text(snapshot.get("title"))
    body = _text(snapshot.get("body"))
    state = _text(snapshot.get("state"))
    if number is None or not title:
        raise ValueError("PR snapshot requires number and title")
    content = f"PR #{number} {title}\nstate={state or 'unknown'}"
    if body:
        content += "\n\n" + body
    return GitHubRecord(
        kind="pull_request",
        id=str(number),
        occurred_at=_text(snapshot.get("updated_at") or snapshot.get("created_at")),
        actor=_text((snapshot.get("user") or {}).get("login") if isinstance(snapshot.get("user"), Mapping) else snapshot.get("user")) or "unknown",
        content=content,
        url=_text(snapshot.get("url")) or None,
        conversation_ref=f"github:pr:{number}",
        metadata=_safe_metadata(
            snapshot,
            ("draft", "merged", "mergeable", "base", "head", "base_sha", "head_sha"),
        ),
    )


def record_from_commit_snapshot(snapshot: Mapping[str, Any]) -> GitHubRecord:
    sha = _text(snapshot.get("sha") or (snapshot.get("commit") or {}).get("sha") if isinstance(snapshot.get("commit"), Mapping) else "")
    commit = snapshot.get("commit") if isinstance(snapshot.get("commit"), Mapping) else snapshot
    message = _text(commit.get("message") if isinstance(commit, Mapping) else snapshot.get("message"))
    if not sha or not message:
        raise ValueError("commit snapshot requires sha and message")
    actor = "unknown"
    author = snapshot.get("author")
    if isinstance(author, Mapping):
        actor = _text(author.get("login") or author.get("name")) or actor
    occurred = _text(snapshot.get("created_at"))
    return GitHubRecord(
        kind="commit",
        id=sha,
        occurred_at=occurred,
        actor=actor,
        content=f"Commit {sha[:12]}: {message}",
        url=_text(snapshot.get("html_url") or snapshot.get("url")) or None,
        metadata={"sha": sha},
    )


def record_from_workflow_summary(snapshot: Mapping[str, Any]) -> GitHubRecord:
    run_id = snapshot.get("id")
    name = _text(snapshot.get("name"))
    status = _text(snapshot.get("status"))
    conclusion = _text(snapshot.get("conclusion"))
    if run_id is None or not name:
        raise ValueError("workflow summary requires id and name")
    # Store the bounded outcome, never raw logs.
    content = f"Workflow {name} run {run_id}: status={status or 'unknown'} conclusion={conclusion or 'unknown'}"
    return GitHubRecord(
        kind="workflow_run",
        id=str(run_id),
        occurred_at=_text(snapshot.get("updated_at") or snapshot.get("created_at")),
        actor="github-actions",
        content=content,
        url=_text(snapshot.get("html_url")) or None,
        metadata=_safe_metadata(snapshot, ("run_number", "head_sha", "event")),
    )
