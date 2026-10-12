"""Read-only bridge to the existing Social Runtime keyword.search operation.

No OAuth tokens or browser sessions are read here; only the Social Runtime
account binding and product-scoped API key are accepted via caller injection.
This diagnostic cannot publish, reply, follow, or update persona state.
"""
from datetime import datetime, timezone
import json

SCHEMA = "agentos.mio-keyword-social-runtime-probe/v1"
ACCOUNT = "mio.milkcat"


def diagnose_keyword_runtime(*, binding_id, provider_account_id, binding_username,
                             search_term, read_status):
    report = {"schema": SCHEMA, "status": "BLOCKED", "operation": "keyword.search",
              "account": ACCOUNT, "write_performed": False, "items": [],
              "read_only": True, "result_count": 0}
    if binding_username != ACCOUNT or not isinstance(binding_id, str) or ":persona:" not in binding_id or not str(provider_account_id).isdigit():
        return {**report, "reason": "ACCOUNT_BINDING_UNVERIFIED"}
    if not isinstance(search_term, str) or not 1 <= len(search_term.strip()) <= 60:
        return {**report, "reason": "INVALID_QUERY"}
    request = {"schema": "agentos.social-request/v1", "product_id": "galaxy",
               "platform": "threads", "operation": "keyword.search",
               "account_binding_id": binding_id, "target_account_id": str(provider_account_id),
               "query": search_term.strip(), "search_type": "RECENT",
               "search_mode": "KEYWORD"}
    try:
        status, receipt = read_status(request)
    except (OSError, TimeoutError, ValueError, TypeError):
        return {**report, "reason": "SOCIAL_RUNTIME_UNAVAILABLE"}
    if status != 200 or not isinstance(receipt, dict):
        return {**report, "reason": "SOCIAL_RUNTIME_REJECTED"}
    error = str(receipt.get("error_code") or "")
    if receipt.get("ok") is not True:
        code = "AUTH_SCOPE_REQUIRED" if any(x in error.lower() for x in
               ("permission", "scope", "oauth", "190", "10")) else "SOCIAL_READ_BLOCKED"
        return {**report, "reason": code}
    if (receipt.get("operation") != "keyword.search" or
        receipt.get("account_binding_id") != binding_id or
        str(receipt.get("target_account_id")) != str(provider_account_id) or
        receipt.get("platform") != "threads"):
        return {**report, "reason": "RECEIPT_IDENTITY_MISMATCH"}
    rows = (receipt.get("result") or {}).get("items") if isinstance(receipt.get("result"), dict) else None
    if not isinstance(rows, list) or len(rows) > 10:
        return {**report, "reason": "RESULT_BOUNDS_INVALID"}
    if any(not isinstance(x, dict) for x in rows):
        return {**report, "reason": "RESULT_SCHEMA_INVALID"}
    own_only = bool(rows) and all(str(x.get("username") or "").lower().lstrip("@") == ACCOUNT for x in rows)
    # Runtime's keyword.search does not certify root-post/visibility; return
    # no candidate text until a separate public read confirms provenance.
    return {**report, "status": "UNVERIFIED",
            "reason": "OWN_POSTS_ONLY" if own_only else "EXTERNAL_POST_PROVENANCE_REQUIRED",
            "result_count": len(rows), "source_receipt_id": receipt.get("receipt_id"),
            "source_operation": "keyword.search",
            "fields_observed": sorted(set().union(*(set(row).intersection(
                {"id", "text", "username", "timestamp", "permalink"}) for row in rows)))}
