#!/usr/bin/env python3
"""Read-only X OAuth 1.0a identity probe.

No Post is created and no media is uploaded. Secrets are never printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


ENDPOINT = "https://api.x.com/2/users/me"
KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def pct(value: str) -> str:
    return quote(str(value), safe="~-._")


def oauth_header(method: str, url: str, consumer_key: str, consumer_secret: str, token: str, token_secret: str) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    normalized = "&".join(f"{pct(k)}={pct(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), pct(url), pct(normalized)])
    signing_key = f"{pct(consumer_secret)}&{pct(token_secret)}".encode()
    digest = hmac.new(signing_key, base.encode(), hashlib.sha1).digest()
    params["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(f'{pct(k)}="{pct(v)}"' for k, v in sorted(params.items()))


def classify_http(status: int) -> str:
    if status == 401:
        return "AUTH_REQUIRED"
    if status == 403:
        return "ENTITLEMENT_REQUIRED"
    if status == 429:
        return "RATE_LIMITED"
    if 500 <= status:
        return "DEGRADED"
    return "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-username", default="")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    presence = {name: bool(os.environ.get(name)) for name in KEYS}
    base = {
        "schema": "agentos.x-auth-inspect/v1",
        "credential_presence": presence,
        "authentication_success": False,
        "write_entitlement": "UNKNOWN",
        "media_entitlement": "UNKNOWN",
        "account_identity": None,
        "credential_exposed": False,
        "side_effect": False,
    }
    if not all(presence.values()):
        base["status"] = "AUTH_REQUIRED"
        base["reason"] = "required OAuth 1.0a credentials are not all present"
        print(json.dumps(base, ensure_ascii=False))
        return 2

    header = oauth_header(
        "GET",
        ENDPOINT,
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_SECRET"],
    )
    req = Request(ENDPOINT, headers={"Authorization": header, "Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=args.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        base["status"] = classify_http(exc.code)
        base["http_status"] = exc.code
        base["reason"] = "X identity probe rejected"
        print(json.dumps(base, ensure_ascii=False))
        return 3
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        base["status"] = "DEGRADED"
        base["reason"] = type(exc).__name__
        print(json.dumps(base, ensure_ascii=False))
        return 4

    user = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        base["status"] = "UNKNOWN"
        base["reason"] = "authenticated response did not include user identity"
        print(json.dumps(base, ensure_ascii=False))
        return 5

    username = str(user.get("username") or "")
    base["authentication_success"] = True
    base["account_identity"] = {"id": str(user.get("id")), "username": username}
    if args.expected_username and username.lower() != args.expected_username.lower().lstrip("@"):
        base["status"] = "PERMISSION_DENIED"
        base["reason"] = "authenticated account identity does not match expected account"
        print(json.dumps(base, ensure_ascii=False))
        return 6

    base["status"] = "READY"
    base["reason"] = "identity authentication succeeded; write/media entitlement remains unproven without side effects"
    print(json.dumps(base, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
