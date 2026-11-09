from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DirectMessageEvent:
    platform: str
    account_id: str
    conversation_id: str
    message_id: str
    actor_id: str | None
    actor_username: str | None
    text: str
    timestamp: str | None
    direction: str = "inbound"
    source: str = "web_bridge"
    schema: str = "agentos.social-conversation-event/v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["text"] = str(payload["text"] or "")[:12000]
        return payload


def dedupe_new_events(
    events: Iterable[DirectMessageEvent],
    seen_message_ids: set[str],
) -> list[DirectMessageEvent]:
    out: list[DirectMessageEvent] = []
    local = set(seen_message_ids)
    for event in events:
        mid = str(event.message_id or "").strip()
        if not mid or mid in local:
            continue
        local.add(mid)
        out.append(event)
    return out
