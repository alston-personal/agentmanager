"""Verify Vendor Reputation's existing public Threads resolver as a Mio read source.

Consume a previously obtained response from /v1/threads/resolve; this module
never performs network access, browser automation, login, publication or reply.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit
import re

SCHEMA = "agentos.mio-public-permalink-source/v1"
POST_PATH = re.compile(r"^/@([A-Za-z0-9._]{1,40})/post/([A-Za-z0-9_-]{1,40})$")


def canonical_url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme != "https" or (parts.hostname or "").lower() not in (
        "threads.com", "www.threads.com", "threads.net", "www.threads.net"
    ) or parts.port not in (None, 443):
        return None
    matched = POST_PATH.fullmatch(parts.path.rstrip("/"))
    if not matched or parts.username or parts.password:
        return None
    return "https://www.threads.com" + parts.path.rstrip("/")


def validate_vendor_public_post(*, requested_url, response, source_receipt, observed_at=None):
    """Fail closed unless URL, author, bounded text and receipt correlate."""
    out = {"schema": SCHEMA, "status": "BLOCKED", "items": [],
           "write_allowed": False, "reply_allowed": False, "ir_adoption_allowed": False}
    expected = canonical_url(requested_url)
    if not expected:
        return {**out, "reason": "INVALID_URL"}
    if not isinstance(source_receipt, dict) or source_receipt.get("ok") is not True or not source_receipt.get("receipt_id"):
        return {**out, "reason": "SOURCE_RECEIPT_REQUIRED"}
    if source_receipt.get("operation") != "public.post.resolve" or canonical_url(source_receipt.get("url")) != expected:
        return {**out, "reason": "RECEIPT_URL_MISMATCH"}
    if not isinstance(response, dict) or response.get("schema") != "agentos.social.threads.public-post/v1":
        return {**out, "reason": "READER_SCHEMA_INVALID"}
    if response.get("login_bypass_used") is not False or response.get("anti_bot_bypass_used") is not False:
        return {**out, "reason": "READER_PROVENANCE_INVALID"}
    source = response.get("source")
    if not isinstance(source, dict) or canonical_url(source.get("url")) != expected:
        return {**out, "reason": "SOURCE_URL_MISMATCH"}
    author = POST_PATH.fullmatch(urlsplit(expected).path).group(1)
    if str(source.get("username") or "").lower().lstrip("@") != author.lower():
        return {**out, "reason": "AUTHOR_MISMATCH"}
    if author.lower() == "mio.milkcat":
        return {**out, "reason": "OWN_POST"}
    body = source.get("text")
    if not isinstance(body, str) or not body.strip() or len(body) > 12000:
        return {**out, "reason": "TEXT_INVALID"}
    return {**out, "status": "PASS", "reason": "PUBLIC_POST_RESOLVED",
            "source_receipt_id": source_receipt["receipt_id"],
            "observed_at": observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "items": [{"url": expected, "author": author, "text": body.strip(),
                       "source": "vendor-public-threads-reader", "provenance": "public-post",
                       "content_verified": True, "reply_allowed": False}]}
