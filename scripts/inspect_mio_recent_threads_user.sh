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
                if operation == "keyword.search":
                    error = str(result.get("error_code") or "")
                    if re.fullmatch(r"threads_[a-zA-Z0-9_]{1,100}", error):
                        print("mio_search_api_error=" + error)
                    else:
                        print("mio_search_api_error=unknown_receipt")
                    return {"_keyword_error": error if re.fullmatch(r"threads_[a-zA-Z0-9_]{1,100}", error) else "unknown_receipt"}
                return None
            return result.get("result") or {}
    except urllib.error.HTTPError as exc:
        if operation == "keyword.search":
            print("mio_search_api_error=http_" + str(int(exc.code)))
            return {"_keyword_error": "http_" + str(int(exc.code))}
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        if operation == "keyword.search":
            print("mio_search_api_error=transport")
            return {"_keyword_error": "transport"}
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
verified_matches = [(bid, row) for bid, row in matches if str(row.get("username") or "").lstrip("@").lower() in ("sunlake.milkcat", "mio.milkcat")]
print("mio_oauth_persona_known_handle=" + str(bool(verified_matches)).lower())
print("mio_oauth_persona_known_binding_count=" + str(len(verified_matches)))
if not product_key or not verified_matches:
    fail("BINDING_UNAVAILABLE")
# Read-only Meta debug_token scopes are checked for each candidate without printing tokens.
def effective_keyword_scope(row):
    token = str(row.get("access_token") or "")
    if not token:
        return "missing_token"
    try:
        import urllib.parse
        url = "https://graph.threads.net/debug_token?" + urllib.parse.urlencode({"input_token": token})
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.load(response)
        info = result.get("data") if isinstance(result, dict) else None
        if not isinstance(info, dict):
            return "invalid_response"
        if info.get("is_valid") is False:
            return "token_invalid"
        if not isinstance(info.get("scopes"), list):
            return "scope_field_unavailable"
        return "granted" if "threads_keyword_search" in info["scopes"] else "not_granted"
    except urllib.error.HTTPError as exc:
        return "http_" + str(int(exc.code))
    except (OSError, ValueError, TypeError):
        return "probe_unavailable"

owned_candidates = []
for candidate_bid, candidate_account in verified_matches:
    candidate_posts = read("post.read", candidate_bid, product_key)
    if isinstance(candidate_posts, dict) and any(str(p.get("id") or "") == "18131575054809711" for p in (candidate_posts.get("items") or []) if isinstance(p, dict)):
        owned_candidates.append((candidate_bid, candidate_account, candidate_posts, effective_keyword_scope(candidate_account)))
print("mio_oauth_owned_post_binding_count=" + str(len(owned_candidates)))
if not owned_candidates:
    fail("TARGET_MIO_POST_OWNER_UNAVAILABLE")

# Multiple persona bindings can be aliases for the same provider account.
# Collapse them by provider_account_id and prefer the explicit persona binding.
by_account = {}
for row in owned_candidates:
    candidate_bid, candidate_account, candidate_posts, candidate_scope = row
    account_id = str(candidate_account.get("provider_account_id") or "")
    if not account_id:
        continue
    previous = by_account.get(account_id)
    preferred = candidate_bid == f"galaxy:threads:persona:{account_id}"
    if previous is None or preferred:
        by_account[account_id] = row
if len(by_account) != 1:
    fail("TARGET_MIO_POST_OWNER_AMBIGUOUS")
owned_candidates = list(by_account.values())
granted_candidates = [row for row in owned_candidates if row[3] == "granted"]
print("mio_oauth_owned_post_granted_count=" + str(len(granted_candidates)))
bid, account, posts, scope_result = (granted_candidates[0] if granted_candidates else owned_candidates[0])
if not isinstance(posts, dict):
    fail("POSTS_READ_FAILED")
owned_posts = [p for p in (posts.get("items") or [])
               if isinstance(p, dict) and re.fullmatch(r"[0-9]{10,25}", str(p.get("id") or ""))]
if not owned_posts:
    fail("NO_VERIFIED_OWNED_POSTS")
if not any(str(p.get("id") or "") == "18131575054809711" for p in owned_posts):
    fail("TARGET_MIO_POST_NOT_OWNED")
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
# Persona effective OAuth grant evaluated on the selected post-owning binding above.
print("mio_search_scope_probe=" + scope_result)
# One-time provider HTTP-400 differential test was completed in Oracle Run 36078531124.
# Do not repeat raw-token request variants on subsequent routine read-only patrols.
# Exercise the shared provider's actual read-only keyword search; no social write.
if scope_result == "granted":
    discovery = read("keyword.search", bid, product_key, query="貓咪")
    if isinstance(discovery, dict) and isinstance(discovery.get("items"), list):
        print("mio_social_outbound=SEARCH_READ_PASS")
        print("mio_search_results_count=" + str(len(discovery["items"])))
    else:
        reason = str(discovery.get("_keyword_error") or "unknown") if isinstance(discovery, dict) else "unknown"
        reason = re.sub(r"[^a-zA-Z0-9_]", "", reason)[:34] or "unknown"
        print("mio_social_outbound=SEARCH_READ_FAILED_" + reason)
else:
    print("mio_social_outbound=SEARCH_SKIPPED_SCOPE_" + scope_result)
print("mio_recent_patrol=PASS")
print("mio_recent_patrol_post_count=" + str(len(target_ids)))
print("mio_recent_patrol_failed_reads=" + str(len(failed)))
print("mio_recent_patrol_recent_comment_count=" + str(len(results)))
print("mio_recent_patrol_truncated=" + str(len(results) > LIMIT_ROWS).lower())
print("mio_recent_patrol_public_replies=" + json.dumps(items, ensure_ascii=False, separators=(",", ":")))
PY
