#!/usr/bin/env bash
# Read-only, fixed-object public Threads inspection. No persona decision or post.
set -euo pipefail
[ "$(id -un)" = ubuntu ] || { echo 'mio_squirrel_inspect=WRONG_USER'; exit 2; }
python3 - <<'PY'
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = "17873481411585255"
QUESTION = "18187717183406888"
MIO_REPLY = "18125707952493175"
ENV = Path("/home/ubuntu/.config/agentos/social-runtime.env")
CREDS = Path("/home/ubuntu/.local/state/agentos/social/credentials.json")
API = "http://127.0.0.1:8771/v1/social/status"

def safe_fail(code):
    print("mio_squirrel_inspect=" + code, flush=True)
    raise SystemExit(3)

def read_env():
    values = {}
    for raw in ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values

def status(operation, object_id, binding, key):
    payload = {
        "schema":"agentos.social-request/v1",
        "product_id":"galaxy",
        "platform":"threads",
        "operation":operation,
        "account_binding_id":binding,
    }
    if object_id:
        payload["object_id"] = object_id
    request = urllib.request.Request(
        API,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type":"application/json",
                 "X-AgentOS-Product-Key":key},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as resp:
            result = json.load(resp)
            if resp.status != 200 or result.get("ok") is not True:
                return None
            return result.get("result") or {}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

try:
    cfg = read_env()
    products = json.loads(cfg.get("AGENTOS_SOCIAL_PRODUCTS_JSON") or "{}")
    key = str((products.get("galaxy") or {}).get("api_key") or "")
    store = json.loads(CREDS.read_text(encoding="utf-8"))
    binding = [(bid, row) for bid, row in (store.get("bindings") or {}).items()
               if isinstance(row, dict) and row.get("product_id") == "galaxy"
               and row.get("platform") == "threads"]
except (OSError, ValueError, TypeError):
    safe_fail("LOCAL_CONFIG_UNAVAILABLE")
if not key or len(binding) != 1:
    safe_fail("ACCOUNT_BINDING_UNAVAILABLE")
bid, account = binding[0]
posts = status("post.read", None, bid, key)
if not isinstance(posts, dict) or not any(
    str(post.get("id") or "") == ROOT for post in (posts.get("items") or [])
    if isinstance(post, dict)
):
    safe_fail("ROOT_NOT_VERIFIED_AS_OWNED")

all_items = {}
read_modes = {}
for label, object_id in (("root", ROOT), ("question", QUESTION), ("mio_reply", MIO_REPLY)):
    result = status("replies.read", object_id, bid, key)
    read_modes[label] = "PASS" if isinstance(result, dict) else "UNAVAILABLE"
    for row in ((result or {}).get("items") or []):
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        author = str(row.get("username") or "").lstrip("@").lower()
        parent = str((row.get("replied_to") or {}).get("id") or "")
        if not rid.isdecimal():
            continue
        # Only public replies on the exact owned squirrel post / known thread.
        if (parent in (ROOT, QUESTION, MIO_REPLY)
                or rid in (QUESTION, MIO_REPLY)
                or (label == "root" and author == "faithedennis_0917")):
            all_items[rid] = {
                "id":rid,
                "username":author[:85],
                "text":str(row.get("text") or "")[:500],
                "timestamp":str(row.get("timestamp") or "")[:48],
                "replied_to_id":parent,
                "permalink":str(row.get("permalink") or "")[:280],
                "is_reply_owned_by_me":bool(row.get("is_reply_owned_by_me")),
            }
if read_modes["root"] != "PASS":
    safe_fail("ROOT_COMMENTS_UNAVAILABLE")
values = list(all_items.values())[-40:]
print("mio_squirrel_inspect=PASS")
print("mio_squirrel_read_modes=" + json.dumps(read_modes, separators=(",", ":")))
print("mio_squirrel_public_replies=" + json.dumps(values, ensure_ascii=False, separators=(",", ":")))
PY
