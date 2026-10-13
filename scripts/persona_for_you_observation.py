"""Fail-closed projection for a *separately authorized* Mio For You GUI read.

This module never opens a browser, logs in, scrolls, clicks, replies or
treats page text as a verified public-post provider receipt.
"""
import re

SCHEMA = "agentos.mio-for-you-observation/v1"
HANDLES = re.compile(r"^[A-Za-z0-9._]{1,40}$")
POST = re.compile(r"^https://www\.threads\.com/@([A-Za-z0-9._]{1,40})/post/([A-Za-z0-9_-]{1,40})$")


def project_for_you_snapshot(*, account, page_url, identity_receipt, read_receipt, rows):
    report = {"schema": SCHEMA, "account": "mio.milkcat", "status": "BLOCKED",
              "items": [], "write_allowed": False, "reply_allowed": False,
              "ir_revision_required": False}
    if account != "mio.milkcat":
        return {**report, "reason": "ACCOUNT_MISMATCH"}
    if not isinstance(identity_receipt, dict) or identity_receipt.get("ok") is not True or identity_receipt.get("account") != account or not identity_receipt.get("receipt_id"):
        return {**report, "reason": "IDENTITY_NOT_VERIFIED"}
    if not isinstance(read_receipt, dict) or read_receipt.get("ok") is not True or read_receipt.get("account") != account or read_receipt.get("operation") != "for_you.read" or not read_receipt.get("receipt_id"):
        return {**report, "reason": "READ_RECEIPT_NOT_VERIFIED"}
    if page_url not in ("https://www.threads.com/", "https://www.threads.com"):
        return {**report, "reason": "NOT_FOR_YOU_PAGE"}
    if not isinstance(rows, list) or len(rows) > 20:
        return {**report, "reason": "BOUNDS_INVALID"}
    items = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        match = POST.fullmatch(url) if isinstance(url, str) else None
        if not match:
            continue
        author, code = match.groups()
        if author.lower() == account or not HANDLES.fullmatch(author):
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "author": author, "shortcode": code,
                      "state": "CANDIDATE_URL_ONLY", "content_verified": False,
                      "reply_allowed": False})
    return {**report, "status": "UNVERIFIED",
            "reason": "POST_CONTENT_AND_PARENT_UNVERIFIED",
            "identity_receipt_id": identity_receipt["receipt_id"],
            "read_receipt_id": read_receipt["receipt_id"], "items": items,
            "candidate_count": len(items)}
