from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class DMLoopDecision:
    allow: bool
    reason: str
    fingerprint: str


def normalize_text(value: str) -> str:
    text=re.sub(r"\s+"," ",str(value or "").strip().lower())
    return text[:1000]


def message_fingerprint(*, sender: str, text: str) -> str:
    raw=(str(sender or "").strip().lower()+"\x1f"+normalize_text(text)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def should_auto_reply(
    *,
    event: dict[str, Any],
    state: dict[str, Any],
    own_account: str,
    peer_account: str | None,
    max_auto_hops: int,
    cooldown_seconds: int,
    hop_window_seconds: int = 600,
    now_epoch: float | None = None,
) -> DMLoopDecision:
    direction=str(event.get("direction") or "")
    sender=str(event.get("actor_username") or "").lstrip("@").lower()
    message_id=str(event.get("message_id") or "")
    text=str(event.get("text") or "").strip()

    fp=message_fingerprint(sender=sender,text=text)

    if direction!="inbound":
        return DMLoopDecision(False,"not_inbound",fp)
    if not message_id or not text or not sender:
        return DMLoopDecision(False,"incomplete_event",fp)
    if sender==str(own_account or "").lstrip("@").lower():
        return DMLoopDecision(False,"own_message",fp)
    if peer_account and sender!=str(peer_account).lstrip("@").lower():
        return DMLoopDecision(False,"unexpected_peer",fp)

    processed={str(x) for x in state.get("processed_message_ids") or []}
    if message_id in processed:
        return DMLoopDecision(False,"duplicate_message_id",fp)

    seen_fp={str(x) for x in state.get("processed_fingerprints") or []}
    if fp in seen_fp:
        return DMLoopDecision(False,"semantic_duplicate",fp)

    now=float(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    last=float(state.get("last_auto_reply_epoch") or 0)
    hops=int(state.get("auto_hops") or 0)
    if last>0 and now-last>=max(1,int(hop_window_seconds)):
        hops=0
    if hops>=max(0,int(max_auto_hops)):
        return DMLoopDecision(False,"hop_budget_exhausted",fp)

    if last>0 and now-last<max(0,int(cooldown_seconds)):
        return DMLoopDecision(False,"cooldown",fp)

    return DMLoopDecision(True,"allow",fp)


def record_auto_reply(
    *,
    event: dict[str, Any],
    state: dict[str, Any],
    fingerprint: str,
    now_epoch: float,
) -> dict[str, Any]:
    processed=[str(x) for x in state.get("processed_message_ids") or []]
    fps=[str(x) for x in state.get("processed_fingerprints") or []]
    mid=str(event.get("message_id") or "")
    if mid and mid not in processed:
        processed.append(mid)
    if fingerprint and fingerprint not in fps:
        fps.append(fingerprint)
    return {
        "schema":"agentos.persona-dm-loop-state/v1",
        "processed_message_ids":processed[-5000:],
        "processed_fingerprints":fps[-5000:],
        "auto_hops":int(state.get("auto_hops") or 0)+1,
        "last_auto_reply_epoch":float(now_epoch),
    }


def reset_hop_budget(state: dict[str, Any]) -> dict[str, Any]:
    out=dict(state)
    out["auto_hops"]=0
    return out
