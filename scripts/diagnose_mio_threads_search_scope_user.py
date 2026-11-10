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


def probe_carousel_read() -> tuple[str, str]:
    """Read-only provider check, plus duplicate-publication guard for the approved mountain post."""
    if not CRED_FILE.is_file():
        return "credentials_unavailable", "UNKNOWN"
    try:
        store = json.loads(CRED_FILE.read_text(encoding="utf-8"))
        bindings = [b for b in (store.get("bindings") or {}).values()
                    if isinstance(b, dict) and b.get("product_id") == "galaxy"
                    and b.get("platform") == "threads" and b.get("auth_profile", "persona") == "persona"]
        if len(bindings) != 1 or not str(bindings[0].get("access_token") or ""):
            return "binding_unavailable", "UNKNOWN"
        token = str(bindings[0]["access_token"])
        query = urllib.parse.urlencode({"fields": "id,text,media_type,children,permalink", "limit": "50"})
        req = urllib.request.Request("https://graph.threads.net/me/threads?" + query,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8"))
        posts = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(posts, list):
            return "invalid_response", "UNKNOWN"
        for post in posts:
            if not isinstance(post, dict) or "今天上山，最先來打招呼的是松鼠。" not in str(post.get("text") or ""):
                continue
            children = post.get("children")
            count = len(children.get("data") or []) if isinstance(children, dict) else 0
            media_type = str(post.get("media_type") or "")
            post_id = str(post.get("id") or "")
            permalink = str(post.get("permalink") or "")
            if not post_id.isdecimal() or not permalink.startswith("https://www.threads.com/"):
                return "PASS", "MATCH_INCOMPLETE"
            return "PASS", f"FOUND:{post_id}:{media_type}:{count}:{permalink}"
        return "PASS", "NOT_FOUND_IN_LATEST_50"
    except urllib.error.HTTPError as exc:
        return "http_" + str(int(exc.code)), "UNKNOWN"
    except (OSError, ValueError, TypeError, KeyError):
        return "unavailable", "UNKNOWN"


if __name__ == "__main__":
    try:
        result = probe()
    except Exception:
        result = "probe_unavailable"
    # Never print any token, app ID, account ID, OAuth response, URL, or traceback.
    print("mio_search_scope_probe=" + result)
    read_status, target = probe_carousel_read()
    print("mio_carousel_read_probe=" + read_status)
    print("mio_carousel_existing_target=" + target)
