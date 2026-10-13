"""Bounded, read-only projection of public Threads discovery candidates.

This module does not fetch platform data, infer personas, or publish replies.
The social adapter must separately prove authorized public-read access.
"""
from datetime import datetime, timedelta, timezone
import math
import re

SCHEMA = "agentos.persona-public-discovery/v1"
MAX_ITEMS = 30
MAX_TEXT = 500
ID = re.compile(r"^[0-9]{1,40}$")
HANDLE = re.compile(r"^[A-Za-z0-9_.]{1,40}$")


def _time(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw.strip().replace("Z", "+00:00"))
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def project_public_candidates(*, rows, source_receipt, account, now, seen=(), max_age_hours=72):
    """Accept only source-proven, bounded PUBLIC candidates; never emit an action."""
    if now.tzinfo is None:
        raise ValueError("aware clock required")
    if not isinstance(account, str) or not HANDLE.fullmatch(account.lstrip("@")):
        raise ValueError("account invalid")
    if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
        raise ValueError("unbounded input")
    if not isinstance(max_age_hours, (int, float)) or isinstance(max_age_hours, bool) or not math.isfinite(max_age_hours) or not 0 < max_age_hours <= 168:
        raise ValueError("invalid age window")
    if not isinstance(seen, (list, tuple, set, frozenset)) or len(seen) > 5000:
        raise ValueError("unbounded seen cursor")
    if not isinstance(source_receipt, dict) or source_receipt.get("ok") is not True:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "SOURCE_UNVERIFIED",
                "account": account, "items": [], "write_allowed": False}
    if source_receipt.get("operation") not in ("public.feed.read", "public.post.read"):
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "PUBLIC_ADAPTER_REQUIRED",
                "account": account, "items": [], "write_allowed": False}
    source_account = source_receipt.get("account")
    if not isinstance(source_account, str) or source_account.lstrip("@").lower() != account.lstrip("@").lower():
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "ACCOUNT_MISMATCH",
                "account": account, "items": [], "write_allowed": False}
    receipt_id = source_receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 128:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason": "RECEIPT_MISSING",
                "account": account, "items": [], "write_allowed": False}
    if source_receipt["operation"] == "public.post.read":
        object_id = source_receipt.get("object_id")
        if len(rows) != 1 or not isinstance(object_id, str) or not ID.fullmatch(object_id) or str(rows[0].get("id", "")) != object_id:
            return {"schema": SCHEMA, "status": "BLOCKED", "reason": "OBJECT_ID_MISMATCH",
                    "account": account, "items": [], "write_allowed": False}
    seen_ids = set(str(i) for i in seen)
    accepted, deduped, rejected = [], set(), 0
    clock = now.astimezone(timezone.utc)
    for item in rows:
        if not isinstance(item, dict) or item.get("visibility") != "public":
            rejected += 1
            continue
        post_id, root_id = str(item.get("id", "")), str(item.get("root_id", ""))
        author = str(item.get("username", "")).lstrip("@").lower()
        created = _time(item.get("timestamp"))
        text = item.get("text")
        if (not ID.fullmatch(post_id) or not ID.fullmatch(root_id)
                or not HANDLE.fullmatch(author) or author == account.lstrip("@").lower()
                or not created or not (clock - timedelta(hours=max_age_hours) <= created <= clock)
                or not isinstance(text, str) or not text.strip()):
            rejected += 1
            continue
        key = (author, post_id, root_id)
        if key in deduped or post_id in seen_ids:
            rejected += 1
            continue
        deduped.add(key)
        accepted.append({"post_id": post_id, "root_id": root_id, "author": author,
                         "observed_post_at": created.isoformat().replace("+00:00", "Z"),
                         "text_excerpt": text[:MAX_TEXT], "source_receipt_id": receipt_id,
                         "decision": "UNDECIDED", "reply_allowed": False})
    return {"schema": SCHEMA, "status": "PASS", "account": account,
            "source_receipt_id": receipt_id, "items": accepted,
            "rejected_count": rejected, "write_allowed": False,
            "functional_acceptance": "NOT_EVALUATED"}
