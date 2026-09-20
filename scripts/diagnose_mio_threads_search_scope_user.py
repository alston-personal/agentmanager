#!/usr/bin/env python3
"""Read-only Meta Threads token capability check. Print booleans only."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_FILE = Path("/home/ubuntu/.config/agentos/social-runtime.env")
CRED_FILE = Path("/home/ubuntu/.local/state/agentos/social/credentials.json")


def probe() -> str:
    if not ENV_FILE.is_file() or not CRED_FILE.is_file():
        return "runtime_credentials_unavailable"
    store = json.loads(CRED_FILE.read_text(encoding="utf-8"))
    bindings = [
        b for b in (store.get("bindings") or {}).values()
        if isinstance(b, dict) and b.get("product_id") == "galaxy"
        and b.get("platform") == "threads" and b.get("auth_profile", "persona") == "persona"
    ]
    if len(bindings) != 1:
        return "binding_not_unique"
    token = str(bindings[0].get("access_token") or "")
    if not token:
        return "missing_token"
    url = "https://graph.threads.net/debug_token?" + urllib.parse.urlencode({"input_token": token})
    request = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return "http_" + str(int(exc.code))
    except (OSError, ValueError, TypeError):
        return "probe_unavailable"
    info = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(info, dict):
        return "invalid_response"
    if info.get("is_valid") is False:
        return "token_invalid"
    scopes = info.get("scopes")
    if not isinstance(scopes, list):
        return "scope_field_unavailable"
    return "granted" if "threads_keyword_search" in scopes else "not_granted"


if __name__ == "__main__":
    try:
        result = probe()
    except Exception:
        result = "probe_unavailable"
    # Never print any token, app ID, account ID, OAuth response, URL, or traceback.
    print("mio_search_scope_probe=" + result)
