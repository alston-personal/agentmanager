"""
Threads, X (Twitter), Bluesky, and Generic Adapters for Social Galaxy
"""
from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timezone
from .base import BaseSocialAdapter
from ..models import CanonicalSocialEvent


class ThreadsAdapter(BaseSocialAdapter):
    @property
    def platform_name(self) -> str:
        return "threads"

    def parse_raw_event(self, raw: Dict[str, Any]) -> CanonicalSocialEvent:
        # 支援 Threads API 與 Web Reader 格式
        event_id = str(raw.get("id") or f"threads:{raw.get('timestamp')}")
        actor = raw.get("actor_username") or raw.get("username") or raw.get("from") or "unknown"
        target = raw.get("target_username") or raw.get("replied_to_username") or raw.get("to") or "unknown"
        ev_type = "quote" if raw.get("is_quote_post") else (raw.get("event_type") or "reply")

        return CanonicalSocialEvent(
            id=f"threads:{event_id}" if not event_id.startswith("threads:") else event_id,
            source="threads",
            actor_id=f"threads:{actor.lstrip('@').lower()}",
            actor_name=f"@{actor.lstrip('@')}",
            target_id=f"threads:{target.lstrip('@').lower()}",
            target_name=f"@{target.lstrip('@')}",
            event_type=str(ev_type).lower(),
            timestamp=raw.get("timestamp") or raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
            confidence=float(raw.get("confidence", 1.0)),
            meta=raw.get("meta", {}),
        )


class XAdapter(BaseSocialAdapter):
    @property
    def platform_name(self) -> str:
        return "x"

    def parse_raw_event(self, raw: Dict[str, Any]) -> CanonicalSocialEvent:
        # 支援 Twitter API v2 (Tweets, Mentions, Retweets, Quotes)
        tweet_id = str(raw.get("id") or raw.get("tweet_id") or "0")
        author = raw.get("author_username") or raw.get("username") or raw.get("user", {}).get("screen_name") or "unknown"
        target = raw.get("in_reply_to_username") or raw.get("target_username") or "unknown"
        
        # 判斷類型
        raw_type = raw.get("type") or raw.get("event_type")
        if not raw_type:
            if raw.get("referenced_tweets"):
                ref = raw["referenced_tweets"][0]["type"]
                raw_type = "repost" if ref == "retweeted" else ("quote" if ref == "quoted" else "reply")
            else:
                raw_type = "mention"

        return CanonicalSocialEvent(
            id=f"x:{tweet_id}" if not tweet_id.startswith("x:") else tweet_id,
            source="x",
            actor_id=f"x:{author.lstrip('@').lower()}",
            actor_name=f"@{author.lstrip('@')}",
            target_id=f"x:{target.lstrip('@').lower()}",
            target_name=f"@{target.lstrip('@')}",
            event_type=str(raw_type).lower(),
            timestamp=raw.get("created_at") or raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            confidence=float(raw.get("confidence", 1.0)),
            meta=raw.get("meta", {}),
        )


class BlueskyAdapter(BaseSocialAdapter):
    @property
    def platform_name(self) -> str:
        return "bluesky"

    def parse_raw_event(self, raw: Dict[str, Any]) -> CanonicalSocialEvent:
        # 支援 AT Protocol (app.bsky.feed.post, repost, like)
        cid = str(raw.get("cid") or raw.get("uri") or raw.get("id") or "unknown")
        author_handle = raw.get("author", {}).get("handle") or raw.get("author_handle") or raw.get("handle") or "unknown"
        target_handle = raw.get("reply", {}).get("parent", {}).get("author", {}).get("handle") or raw.get("target_handle") or "unknown"
        
        ev_type = "reply" if raw.get("reply") else ("repost" if "repost" in raw.get("$type", "") else "interaction")

        return CanonicalSocialEvent(
            id=f"bluesky:{cid}" if not cid.startswith("bluesky:") else cid,
            source="bluesky",
            actor_id=f"bluesky:{author_handle.lower()}",
            actor_name=f"@{author_handle}",
            target_id=f"bluesky:{target_handle.lower()}",
            target_name=f"@{target_handle}",
            event_type=str(ev_type).lower(),
            timestamp=raw.get("createdAt") or raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            confidence=float(raw.get("confidence", 1.0)),
            meta={"uri": raw.get("uri"), "cid": raw.get("cid")},
        )


class GenericSocialAdapter(BaseSocialAdapter):
    @property
    def platform_name(self) -> str:
        return "generic"

    def parse_raw_event(self, raw: Dict[str, Any]) -> CanonicalSocialEvent:
        src = str(raw.get("source") or "generic").lower()
        actor = str(raw.get("actor_id") or raw.get("actor") or raw.get("from") or "unknown")
        target = str(raw.get("target_id") or raw.get("target") or raw.get("to") or "unknown")

        return CanonicalSocialEvent(
            id=str(raw.get("id") or f"{src}:{actor}:{target}:{raw.get('timestamp')}"),
            source=src,
            actor_id=actor if ":" in actor else f"{src}:{actor.lower()}",
            actor_name=str(raw.get("actor_name") or actor),
            target_id=target if ":" in target else f"{src}:{target.lower()}",
            target_name=str(raw.get("target_name") or target),
            event_type=str(raw.get("event_type") or raw.get("type") or "interaction").lower(),
            timestamp=raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            confidence=float(raw.get("confidence", 1.0)),
            meta=raw.get("meta", {}),
        )
