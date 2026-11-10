from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class CheckpointPolicy:
    checkpoints_minutes: tuple[int, ...] = (60, 360, 1440)
    fast_follow_minutes: int = 120

    def next_checkpoint_minutes(self, elapsed_minutes: int, needs_attention: bool) -> int | None:
        if needs_attention:
            return elapsed_minutes + self.fast_follow_minutes
        for minute in self.checkpoints_minutes:
            if minute > elapsed_minutes:
                return minute
        return None


def build_snapshot(*, experiment_id: str, account_username: str, post: dict[str, Any],
                   replies: list[dict[str, Any]], previous_reply_ids: set[str],
                   captured_at: str | None = None) -> dict[str, Any]:
    now = captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    reply_ids = [str(x.get("id") or "") for x in replies if x.get("id")]
    new = [x for x in replies if str(x.get("id") or "") not in previous_reply_ids]
    return {
        "schema": "agentos.social-post-experiment-snapshot/v1",
        "captured_at": now,
        "experiment_id": experiment_id,
        "account_username": account_username,
        "post": {
            "id": str(post.get("id") or ""),
            "permalink": post.get("permalink"),
            "text": post.get("text"),
            "media_type": post.get("media_type"),
            "timestamp": post.get("timestamp"),
        },
        "reply_count": len(replies),
        "reply_ids": reply_ids,
        "new_replies": [
            {
                "id": x.get("id"),
                "username": x.get("username"),
                "text": x.get("text"),
                "timestamp": x.get("timestamp"),
                "permalink": x.get("permalink"),
                "is_reply_owned_by_me": bool(x.get("is_reply_owned_by_me")),
            }
            for x in new
        ],
        "needs_attention": bool(new),
    }


def learning_record(snapshot: dict[str, Any], *, elapsed_minutes: int,
                    observed_metrics: dict[str, Any] | None = None,
                    hypothesis: str = "", changed_variables: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema": "agentos.social-post-learning-observation/v1",
        "experiment_id": snapshot["experiment_id"],
        "account_username": snapshot["account_username"],
        "post_id": snapshot["post"]["id"],
        "captured_at": snapshot["captured_at"],
        "elapsed_minutes": int(elapsed_minutes),
        "hypothesis": hypothesis,
        "changed_variables": list(changed_variables or []),
        "metrics": dict(observed_metrics or {}),
        "reply_count": int(snapshot.get("reply_count") or 0),
        "new_reply_count": len(snapshot.get("new_replies") or []),
        "needs_attention": bool(snapshot.get("needs_attention")),
    }


def next_observation(policy: CheckpointPolicy, *, elapsed_minutes: int,
                     snapshot: dict[str, Any]) -> dict[str, Any]:
    next_minute = policy.next_checkpoint_minutes(elapsed_minutes, bool(snapshot.get("needs_attention")))
    return {
        "schema": "agentos.social-post-next-observation/v1",
        "experiment_id": snapshot["experiment_id"],
        "post_id": snapshot["post"]["id"],
        "current_elapsed_minutes": int(elapsed_minutes),
        "next_elapsed_minutes": next_minute,
        "reason": "fast_follow_on_attention" if snapshot.get("needs_attention") else "scheduled_learning_checkpoint",
        "complete": next_minute is None,
    }
