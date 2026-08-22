"""Transport-neutral contracts for read-only ExperienceEvent source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from runtime_core.experience_ir import ExperienceBatch


@dataclass(frozen=True)
class SourceCursor:
    source_kind: str
    position: str | None = None

    def __post_init__(self) -> None:
        if not str(self.source_kind or "").strip():
            raise ValueError("source_kind is required")


@dataclass(frozen=True)
class SourcePage:
    batch: ExperienceBatch
    next_cursor: SourceCursor | None
    has_more: bool = False

    def __post_init__(self) -> None:
        if self.has_more and self.next_cursor is None:
            raise ValueError("has_more requires next_cursor")


class ExperienceSourceAdapter(Protocol):
    """Read-only ingestion boundary. Credentials never enter ExperienceEvent."""

    source_kind: str

    def fetch_page(
        self,
        project_id: str,
        cursor: SourceCursor | None = None,
        *,
        limit: int = 50,
    ) -> SourcePage: ...
