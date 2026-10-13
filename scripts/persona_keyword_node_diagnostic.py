#!/usr/bin/env python3
"""Oracle-side, read-only keyword.search diagnostic using existing Social Runtime.

Not a social writer or automatic scheduler. Credentials stay on Oracle; only
a sanitized no-post-text receipt is written. Do not use a browser profile.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from scripts.persona_social_executor import ENV, CREDS, parse_env, find_binding, post
from scripts.persona_keyword_social_runtime_bridge import diagnose_keyword_runtime


def run_probe(query, *, env_path=ENV, credentials_path=CREDS, read_status=None):
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    blocked = {"schema": "agentos.mio-keyword-node-diagnostic/v1",
               "checked_at": stamp, "status": "BLOCKED", "write_performed": False,
               "operation": "keyword.search", "node_verified": False}
    try:
        env = parse_env(Path(env_path))
        products = json.loads(env["AGENTOS_SOCIAL_PRODUCTS_JSON"])
        key = str(products["galaxy"]["api_key"])
        credentials = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
        binding_id, binding = find_binding(credentials, "mio.milkcat")
        if not binding_id or not binding or not key:
            return {**blocked, "reason": "BINDING_OR_PRODUCT_KEY_UNAVAILABLE"}
        reader = read_status or (lambda req: post("/v1/social/status", req,
                                                  {"X-AgentOS-Product-Key": key}))
        result = diagnose_keyword_runtime(binding_id=binding_id,
                 provider_account_id=binding.get("provider_account_id"),
                 binding_username=binding.get("username"), search_term=query,
                 read_status=reader)
        return {**blocked, **result, "checked_at": stamp, "node_verified": False}
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {**blocked, "reason": "RUNTIME_CONFIG_UNAVAILABLE"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--receipt-out", required=True)
    args = ap.parse_args()
    result = run_probe(args.query)
    target = Path(args.receipt_out)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    target.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False))
    # A denied OAuth scope is a safe completed diagnosis, not a success claim.
    return 0 if result.get("status") in ("BLOCKED", "UNVERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
