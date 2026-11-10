from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
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
    caption = post.get("text")
    # Never hash missing/truncated placeholders as if they were a complete post.
    caption_sha256 = hashlib.sha256(caption.encode("utf-8")).hexdigest() if isinstance(caption, str) and caption.strip() else None
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
            "caption_sha256": caption_sha256,
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
                    hypothesis: str = "", changed_variables: list[str] | None = None,
                    insights_status: str = "unverified") -> dict[str, Any]:
    """Extend the existing v1 observation; never upgrade a hypothesis to proof."""
    if elapsed_minutes < 0:
        raise ValueError("social_experiment_elapsed_minutes_negative")
    metrics = dict(observed_metrics or {})
    if not all(isinstance(name, str) and name for name in metrics):
        raise ValueError("social_experiment_metric_name_invalid")
    # Existing Threads adapters may return nested or textual metric values.
    # Retain those observations without breaking v1 callers, but never treat
    # them as verified quantitative evidence.
    numeric_metrics = bool(metrics) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        and math.isfinite(v) for v in metrics.values()
    )
    # Maturity is the age at the *actual* snapshot, not the publishing hour.
    maturity = ("early" if elapsed_minutes < 1440 else
                "developing" if elapsed_minutes < 10080 else "mature")
    post = snapshot["post"]
    caption_digest = post.get("caption_sha256")
    evidence_ready = bool(caption_digest and insights_status == "pass" and numeric_metrics)
    # A validated source read is not an approved causal/strategy learning case.
    # The latter needs an independent coverage/confound review before promotion.
    eligible = False
    return {
        "schema": "agentos.social-post-learning-observation/v1",
        "experiment_id": snapshot["experiment_id"],
        "account_username": snapshot["account_username"],
        "post_id": snapshot["post"]["id"],
        "caption_sha256": caption_digest,
        "captured_at": snapshot["captured_at"],
        "platform": "threads",
        "maturity": maturity,
        "analysis_status": "candidate" if evidence_ready else "pending",
        "source_evidence_ready": evidence_ready,
        "analysis_eligible": eligible,
        "causal_claim_allowed": False,
        "insights_status": insights_status,
        "metric_precision": {key: "provider_unverified" for key in metrics},
        "elapsed_minutes": int(elapsed_minutes),
        "hypothesis": hypothesis,
        "changed_variables": list(changed_variables or []),
        "metrics": metrics,
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
