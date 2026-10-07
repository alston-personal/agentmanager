from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


RESUMABLE_STATES = {"active", "suspended", "assigned", "blocked"}


@dataclass(frozen=True)
class ContinuationOrigin:
    node_id: str | None = None
    executor_id: str | None = None
    participant_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class ContinuationResolution:
    work_id: str | None
    source: str
    binding: dict[str, Any] | None = None


class ContinuationResolver:
    """Resolve an implicit "continue" request without leaking work across scopes.

    The resolver is deliberately transport-agnostic. Persistent stores can project
    their work bindings into dictionaries and reuse this policy before prompting a
    model or dispatching an executor.
    """

    def resolve(
        self,
        bindings: Iterable[dict[str, Any]],
        *,
        origin: ContinuationOrigin,
        explicit_work_id: str | None = None,
    ) -> ContinuationResolution:
        candidates = [
            dict(item)
            for item in bindings
            if str(item.get("state") or "active") in RESUMABLE_STATES
            and item.get("work_id")
        ]

        if explicit_work_id:
            match = self._latest(
                item for item in candidates
                if str(item.get("work_id")) == explicit_work_id
            )
            if match is not None:
                return ContinuationResolution(explicit_work_id, "explicit_work", match)
            return ContinuationResolution(None, "explicit_work_not_found", None)

        selectors = [
            (
                "session",
                lambda item: bool(origin.session_id)
                and item.get("session_id") == origin.session_id,
            ),
            (
                "participant_executor",
                lambda item: bool(origin.node_id and origin.executor_id and origin.participant_id)
                and item.get("node_id") == origin.node_id
                and item.get("executor_id") == origin.executor_id
                and item.get("participant_id") == origin.participant_id,
            ),
            (
                "executor",
                lambda item: bool(origin.node_id and origin.executor_id)
                and item.get("node_id") == origin.node_id
                and item.get("executor_id") == origin.executor_id,
            ),
            (
                "node",
                lambda item: bool(origin.node_id)
                and item.get("node_id") == origin.node_id
                and bool(item.get("node_assigned", False)),
            ),
            (
                "global_assignment",
                lambda item: bool(item.get("global_assigned", False))
                and (
                    not item.get("node_id")
                    or not origin.node_id
                    or item.get("node_id") == origin.node_id
                ),
            ),
        ]

        for source, predicate in selectors:
            match = self._latest(item for item in candidates if predicate(item))
            if match is not None:
                return ContinuationResolution(str(match["work_id"]), source, match)

        return ContinuationResolution(None, "no_continuation", None)

    @staticmethod
    def _latest(items: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
        matches = list(items)
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                str(item.get("updated_at") or ""),
                str(item.get("work_id") or ""),
            ),
        )
