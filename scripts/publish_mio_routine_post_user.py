#!/usr/bin/env python3
"""Mio one-shot governed Threads publish. Never invoked directly by a push workflow.

The Oracle-side operator supplies a reviewed, local JSON intent file (0600), with
post_key and primary_text. No credentials or arbitrary paths are accepted via intent.
"""
import fcntl
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/home/ubuntu/.config/agentos/social-runtime.env")
CREDS = Path("/home/ubuntu/.local/state/agentos/social/credentials.json")
INTENT = Path("/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/approved-post.json")
RECEIPTS = Path("/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/published")
BASE = "http://127.0.0.1:8771"
ACCOUNT = "sunlake.milkcat"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def post(path, payload, headers):
    request = urllib.request.Request(BASE + path, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"content-type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        except Exception:
            return error.code, {"error_code": "invalid_provider_response"}

def main():
    if os.geteuid() != 1001 or not INTENT.is_file() or INTENT.stat().st_mode & 0o077:
        raise SystemExit("mio_publish=PRECONDITION_FAILED")
    intent = load(INTENT)
    key = intent.get("post_key")
    text = intent.get("primary_text")
    if not isinstance(key, str) or not key.startswith("mio-") or len(key) > 90 or not all(c.isalnum() or c == "-" for c in key):
        raise SystemExit("mio_publish=INVALID_POST_KEY")
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise SystemExit("mio_publish=INVALID_TEXT")
    # A local intent file is only data; its presence never grants publish authority.
    # Bind the approved text to the exact reviewed content hash.
    if intent.get("approved_text_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
        raise SystemExit("mio_publish=CONTENT_APPROVAL_MISSING")
    env = {}
    for raw in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            k, v = raw.split("=", 1)
            env[k] = v.strip().strip("\"'")
    products = json.loads(env.get("AGENTOS_SOCIAL_PRODUCTS_JSON", "{}"))
    product_key = (products.get("galaxy") or {}).get("api_key")
    control_token = env.get("AGENTOS_SOCIAL_CONTROL_TOKEN")
    bindings = [(k, v) for k, v in (load(CREDS).get("bindings") or {}).items()
        if isinstance(v, dict) and v.get("product_id") == "galaxy"
        and v.get("platform") == "threads"
        and str(v.get("username", "")).lstrip("@").lower() == ACCOUNT
        and v.get("auth_profile") == "persona"]
    if len(bindings) != 1 or not product_key or not control_token:
        raise SystemExit("mio_publish=ACCOUNT_OR_AUTH_UNAVAILABLE")
    binding_id, account = bindings[0]
    account_id = str(account.get("provider_account_id") or "")
    if not account_id:
        raise SystemExit("mio_publish=ACCOUNT_ID_MISSING")
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    os.chmod(RECEIPTS, 0o700)
    marker = RECEIPTS / (key + ".json")
    # An exclusive, process-held lock prevents two scheduled runs from publishing concurrently.
    lock = RECEIPTS / (key + ".lock")
    lock_fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    if marker.exists():
        receipt = load(marker)
        if receipt.get("post_text_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            raise SystemExit("mio_publish=POST_KEY_CONTENT_COLLISION")
        if receipt.get("ok") and receipt.get("platform_object_id"):
            print("mio_publish=ALREADY_RECORDED")
            print("mio_publish_permalink=" + str(receipt.get("permalink") or ""))
            return
    headers = {"X-AgentOS-Product-Key": product_key}
    read = {"schema": "agentos.social-request/v1", "product_id": "galaxy",
            "platform": "threads", "operation": "post.read", "account_binding_id": binding_id}
    status, existing = post("/v1/social/status", read, headers)
    if status != 200 or existing.get("ok") is not True:
        raise SystemExit("mio_publish=PREPUBLISH_READ_FAILED")
    matches = [p for p in ((existing.get("result") or {}).get("items") or [])
        if str(p.get("text") or "").strip() == text.strip()]
    if matches:
        found = matches[0]
        receipt = {"ok": True, "already_present": True, "platform_object_id": found.get("id"),
                   "permalink": found.get("permalink"), "post_key": key,
                   "post_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    else:
        write = {"schema": "agentos.social-request/v1", "product_id": "galaxy",
            "platform": "threads", "operation": "publish", "account_binding_id": binding_id,
            "target_account_id": account_id, "primary_text": text, "write_intent_id": key}
        status, acceptance = post("/internal/v1/social/acceptances", write,
            {"X-AgentOS-Control-Token": control_token})
        if status != 201 or not acceptance.get("acceptance_id"):
            raise SystemExit("mio_publish=ACCEPTANCE_DENIED")
        status, result = post("/v1/social/publish", write,
            {**headers, "X-AgentOS-Acceptance-ID": str(acceptance["acceptance_id"])})
        if status != 200 or result.get("ok") is not True:
            raise SystemExit("mio_publish=PROVIDER_FAILED_VERIFY_BEFORE_RETRY")
        obj = str(result.get("platform_object_id") or "")
        if not obj:
            raise SystemExit("mio_publish=AMBIGUOUS_PROVIDER_SUCCESS_VERIFY_MANUALLY")
        status, verified = post("/v1/social/status", read, headers)
        rows = ((verified.get("result") or {}).get("items") or []) if status == 200 and verified.get("ok") else []
        found = next((p for p in rows if str(p.get("id") or "") == obj), {})
        if not found:
            raise SystemExit("mio_publish=POST_CREATED_BUT_READBACK_PENDING_VERIFY_MANUALLY")
        receipt = {"ok": True, "already_present": False, "platform_object_id": obj,
                   "permalink": found.get("permalink"), "post_key": key,
                   "post_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if not receipt.get("platform_object_id") or not receipt.get("permalink"):
        raise SystemExit("mio_publish=INCOMPLETE_RECEIPT_VERIFY_MANUALLY")
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(marker)
    print("mio_publish=PASS")
    print("mio_publish_object_id=" + str(receipt.get("platform_object_id") or ""))
    print("mio_publish_permalink=" + str(receipt.get("permalink") or ""))

if __name__ == "__main__":
    main()
