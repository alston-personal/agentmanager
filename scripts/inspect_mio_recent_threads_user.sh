#!/usr/bin/env bash
# Fixed-scope public Threads reading: no persona model, posting, or private messages.
set -euo pipefail
[ "$(id -un)" = ubuntu ] || { echo 'mio_recent_patrol=WRONG_USER'; exit 2; }
python3 - <<'PY'
from __future__ import annotations
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV = Path("/home/ubuntu/.config/agentos/social-runtime.env")
CREDS = Path("/home/ubuntu/.local/state/agentos/social/credentials.json")
API = "http://127.0.0.1:8771/v1/social/status"
# Verify the newest owned posts, plus the known squirrel/first experiment roots.
EXTRA_ROOTS = ("17873481411585255", "18353956147218749")
LIMIT_POSTS = 14
LIMIT_ROWS = 36
SINCE = datetime.now(timezone.utc) - timedelta(hours=42)

def fail(category):
    print("mio_recent_patrol=" + category, flush=True)
    raise SystemExit(3)

def parse_env():
    out = {}
    for raw in ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out

def read(operation, binding, key, object_id=None, query=None):
    payload = {
        "schema": "agentos.social-request/v1",
        "product_id": "galaxy",
        "platform": "threads",
        "operation": operation,
        "account_binding_id": binding,
    }
    if object_id is not None:
        payload["object_id"] = object_id
    if query is not None:
        payload["query"] = query
    request = urllib.request.Request(
        API, method="POST",
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AgentOS-Product-Key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=16) as response:
            result = json.load(response)
            if response.status != 200 or result.get("ok") is not True:
                return None
            return result.get("result") or {}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

def datetime_or_none(raw):
    if not raw:
        return None
    try:
        value = str(raw).replace("Z", "+00:00")
        if re.fullmatch(r".*[+-][0-9]{4}", value):
            value = value[:-5] + value[-5:-2] + ":" + value[-2:]
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None

try:
    env = parse_env()
    product_key = str((json.loads(env.get("AGENTOS_SOCIAL_PRODUCTS_JSON") or "{}").get("galaxy") or {}).get("api_key") or "")
    cred = json.loads(CREDS.read_text(encoding="utf-8"))
    matches = [(bid, row) for bid, row in (cred.get("bindings") or {}).items()
               if isinstance(row, dict) and row.get("product_id") == "galaxy"
               and row.get("platform") == "threads" and row.get("auth_profile", "persona") == "persona"]
except (OSError, ValueError, TypeError, AttributeError):
    fail("CONFIG_UNAVAILABLE")
print("mio_oauth_product_configured=" + str(bool(product_key)).lower())
print("mio_oauth_persona_binding_count=" + str(len(matches)))
print("mio_oauth_viewer_binding_count=" + str(sum(1 for b in (cred.get("bindings") or {}).values() if isinstance(b, dict) and b.get("product_id") == "galaxy" and b.get("platform") == "threads" and b.get("auth_profile") == "viewer")))
print("mio_oauth_persona_known_handle=" + str(any(str(row.get("username") or "").lstrip("@").lower() in ("sunlake.milkcat","mio.milkcat") for _, row in matches)).lower())
if not product_key or len(matches) != 1:
    fail("BINDING_UNAVAILABLE")
bid, account = matches[0]
posts = read("post.read", bid, product_key)
if not isinstance(posts, dict):
    fail("POSTS_READ_FAILED")
owned_posts = [p for p in (posts.get("items") or [])
               if isinstance(p, dict) and re.fullmatch(r"[0-9]{10,25}", str(p.get("id") or ""))]
if not owned_posts:
    fail("NO_VERIFIED_OWNED_POSTS")
by_id = {str(p["id"]): p for p in owned_posts}
target_ids = list(by_id)[:LIMIT_POSTS]
for root in EXTRA_ROOTS:
    if root in by_id and root not in target_ids:
        target_ids.append(root)
results = {}
failed = []
seen_total = 0
for root in target_ids:
    post = by_id[root]
    # Read recent posts even if provider has_replies=false: indicator may lag.
    if target_ids.index(root) >= 7 and post.get("has_replies") is False and root not in EXTRA_ROOTS:
        continue
    replies = read("replies.read", bid, product_key, root)
    if not isinstance(replies, dict):
        failed.append(root)
        continue
    for row in replies.get("items") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        if not re.fullmatch(r"[0-9]{10,25}", rid):
            continue
        at = datetime_or_none(row.get("timestamp"))
        # Keep recent public exchange and a small amount of parent context;
        # older comments should not be reactivated by this one-time patrol.
        if at is None or at < SINCE:
            continue
        seen_total += 1
        parent = str((row.get("replied_to") or {}).get("id") or "")
        results[rid] = {
            "id": rid,
            "root_post_id": root,
            "root_post_text": str(post.get("text") or "")[:115],
            "username": str(row.get("username") or "")[:70].lstrip("@"),
            "text": str(row.get("text") or "")[:290],
            "timestamp": str(row.get("timestamp") or "")[:48],
            "replied_to_id": parent,
            "permalink": str(row.get("permalink") or "")[:135],
            "is_reply_owned_by_me": bool(row.get("is_reply_owned_by_me")),
        }
items = sorted(results.values(), key=lambda x: (x["timestamp"], x["id"]))
if len(items) > LIMIT_ROWS:
    items = items[-LIMIT_ROWS:]
# User-confirmed OAuth reauthorization 2026-09-25: read-only effective scope + API probe.
# Never print credential contents, input tokens, provider responses, or account identifiers.
scope_result = "probe_unavailable"
try:
    token = str(account.get("access_token") or "")
    if not token:
        scope_result = "missing_token"
    else:
        import urllib.parse
        debug_url = "https://graph.threads.net/debug_token?" + urllib.parse.urlencode({"input_token": token})
        debug_req = urllib.request.Request(debug_url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(debug_req, timeout=15) as resp:
            info = json.load(resp)
        data = info.get("data") if isinstance(info, dict) else None
        if not isinstance(data, dict):
            scope_result = "invalid_response"
        elif data.get("is_valid") is False:
            scope_result = "token_invalid"
        elif not isinstance(data.get("scopes"), list):
            scope_result = "scope_field_unavailable"
        else:
            scope_result = "granted" if "threads_keyword_search" in data["scopes"] else "not_granted"
except urllib.error.HTTPError as exc:
    scope_result = "http_" + str(int(exc.code))
except (OSError, ValueError, TypeError):
    scope_result = "probe_unavailable"
print("mio_search_scope_probe=" + scope_result)
# Exercise the shared provider's actual read-only keyword search; no social write.
if scope_result == "granted":
    discovery = read("keyword.search", bid, product_key, query="貓咪")
    if isinstance(discovery, dict) and isinstance(discovery.get("items"), list):
        print("mio_social_outbound=SEARCH_READ_PASS")
        print("mio_search_results_count=" + str(len(discovery["items"])))
    else:
        print("mio_social_outbound=SEARCH_READ_FAILED")
else:
    print("mio_social_outbound=SEARCH_SKIPPED_SCOPE_" + scope_result)
print("mio_recent_patrol=PASS")
print("mio_recent_patrol_post_count=" + str(len(target_ids)))
print("mio_recent_patrol_failed_reads=" + str(len(failed)))
print("mio_recent_patrol_recent_comment_count=" + str(len(results)))
print("mio_recent_patrol_truncated=" + str(len(results) > LIMIT_ROWS).lower())
print("mio_recent_patrol_public_replies=" + json.dumps(items, ensure_ascii=False, separators=(",", ":")))
PY
