#!/usr/bin/env python3
"""Bounded official Threads keyword-search diagnostic, never a social writer.

Token must be injected by the approved per-account secrets owner; this tool
never reads another browser profile or tries to refresh/create credentials.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.parse
import urllib.request

SCHEMA = "agentos.persona-public-keyword-probe/v1"
FIELDS = "id,username,text,timestamp,permalink"
HOST = "https://graph.threads.net/keyword_search"

def probe(*, binding_account, expected_account, allowed_scopes, token, query, opener=None):
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {"schema": SCHEMA, "checked_at": stamp, "account": expected_account,
              "operation": "keyword_search", "read_only": True, "write_performed": False,
              "result_count": 0, "items": []}
    if binding_account != expected_account or expected_account != "mio.milkcat":
        return {**report, "status": "BLOCKED", "reason": "ACCOUNT_MISMATCH"}
    if not isinstance(allowed_scopes, (tuple, list, set, frozenset)) or "threads_keyword_search" not in {str(scope).strip() for scope in allowed_scopes}:
        return {**report, "status": "BLOCKED", "reason": "AUTH_SCOPE_REQUIRED"}
    if not isinstance(token, str) or not token:
        return {**report, "status": "BLOCKED", "reason": "TOKEN_UNAVAILABLE"}
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 60:
        return {**report, "status": "BLOCKED", "reason": "INVALID_QUERY"}
    args = urllib.parse.urlencode({"q": query.strip(), "search_type": "RECENT",
                                   "fields": FIELDS, "limit": 5})
    # Send credentials in header, never query string or printed payload.
    req = urllib.request.Request(HOST + "?" + args,
                                 headers={"Authorization": "Bearer " + token,
                                          "Accept": "application/json"})
    try:
        handler = opener or urllib.request.urlopen
        with handler(req, timeout=15) as resp:
            payload = json.loads(resp.read(262144).decode("utf-8"))
    except urllib.error.HTTPError as err:
        category = ("AUTH_OR_SCOPE_DENIED" if err.code in (401, 403) else
                    "RATE_LIMITED" if err.code == 429 else
                    "BAD_REQUEST" if err.code == 400 else "HTTP_ERROR")
        return {**report, "status": "BLOCKED", "reason": category, "http_status": err.code}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {**report, "status": "BLOCKED", "reason": "ADAPTER_UNAVAILABLE"}
    if isinstance(payload, dict) and "error" in payload:
        return {**report, "status": "BLOCKED", "reason": "PROVIDER_ERROR"}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {**report, "status": "BLOCKED", "reason": "INVALID_SOURCE_RESPONSE"}
    # App-review restrictions may return only the authenticated user's own posts.
    # Such a result is NOT evidence of discovery of other accounts.
    rows = payload["data"]
    if rows and all(isinstance(row, dict) and
                    str(row.get("username") or "").lstrip("@").lower() == expected_account
                    for row in rows):
        return {**report, "status": "UNVERIFIED", "reason": "OWN_POSTS_ONLY",
                "result_count": len(rows), "source_kind": "official_threads_keyword_search"}
    # A keyword-search response alone does not attest a root id, visibility,
    # or verified account binding. Keep raw content OUT of the receipt.
    entries = payload["data"]
    if len(entries) > 5 or any(not isinstance(entry, dict) for entry in entries):
        return {**report, "status": "BLOCKED", "reason": "RESULT_SCHEMA_UNEXPECTED"}
    return {**report, "status": "UNVERIFIED", "reason": "POST_PROVENANCE_INCOMPLETE",
            "result_count": len(entries),
            "fields_observed": sorted(set(FIELDS.split(",")).intersection(
                set().union(*(set(x) for x in entries if isinstance(x, dict))))),
            "source_kind": "official_threads_keyword_search",
            "next_step": "verify individual public-post content, root and visibility"}

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--account", default="mio.milkcat")
    cli.add_argument("--query", required=True)
    cli.add_argument("--receipt-out", required=True)
    args = cli.parse_args()
    # Only the approved binding adapter may populate these scoped variables.
    result = probe(binding_account=os.environ.get("AGENTOS_THREADS_BOUND_ACCOUNT"),
                   expected_account=args.account,
                   allowed_scopes=os.environ.get("AGENTOS_THREADS_GRANTED_SCOPES", "").split(","),
                   token=os.environ.get("AGENTOS_THREADS_ACCESS_TOKEN"),
                   query=args.query)
    from pathlib import Path
    dest = Path(args.receipt_out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("UNVERIFIED", "BLOCKED") else 1

if __name__ == "__main__":
    raise SystemExit(main())
