"""Read-only X OAuth 1.0a authentication probe primitives.

The probe performs GET /2/users/me only. It never creates a Post, uploads media,
or exposes credential values. Publish/media entitlement is deliberately left
UNKNOWN unless a separate authoritative provider signal proves it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ENDPOINT = "https://api.x.com/2/users/me"
CREDENTIAL_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def pct(value: str) -> str:
    return quote(str(value), safe="~-._")


def oauth_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
) -> str:
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
    return "OAuth " + ", ".join(
        f'{pct(k)}="{pct(v)}"' for k, v in sorted(params.items())
    )


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


def _base(credentials: Mapping[str, str]) -> dict[str, Any]:
    return {
        "schema": "agentos.x-auth-inspect/v1",
        "credential_presence": {
            name: bool(str(credentials.get(name) or "")) for name in CREDENTIAL_KEYS
        },
        "authentication_success": False,
        "authentication_status": "UNKNOWN",
        "write_entitlement": "UNKNOWN",
        "media_entitlement": "UNKNOWN",
        "account_identity": None,
        "credential_exposed": False,
        "side_effect": False,
    }


def inspect_x_auth(
    credentials: Mapping[str, str],
    *,
    expected_username: str = "",
    timeout: float = 15.0,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    result = _base(credentials)
    if not all(result["credential_presence"].values()):
        result.update(
            {
                "status": "AUTH_REQUIRED",
                "authentication_status": "AUTH_REQUIRED",
                "reason": "required OAuth 1.0a credentials are not all present",
            }
        )
        return result

    header = oauth_header(
        "GET",
        ENDPOINT,
        str(credentials["X_API_KEY"]),
        str(credentials["X_API_SECRET"]),
        str(credentials["X_ACCESS_TOKEN"]),
        str(credentials["X_ACCESS_SECRET"]),
    )
    req = Request(
        ENDPOINT,
        headers={"Authorization": header, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        status = classify_http(exc.code)
        result.update(
            {
                "status": status,
                "authentication_status": status,
                "http_status": exc.code,
                "reason": "X identity probe rejected",
            }
        )
        return result
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        result.update(
            {
                "status": "DEGRADED",
                "authentication_status": "UNKNOWN",
                "reason": type(exc).__name__,
            }
        )
        return result

    user = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        result.update(
            {
                "status": "UNKNOWN",
                "authentication_status": "UNKNOWN",
                "reason": "authenticated response did not include user identity",
            }
        )
        return result

    username = str(user.get("username") or "")
    result["authentication_success"] = True
    result["authentication_status"] = "READY"
    result["account_identity"] = {"id": str(user.get("id")), "username": username}

    expected = str(expected_username or "").strip().lstrip("@")
    if expected and username.casefold() != expected.casefold():
        result.update(
            {
                "status": "PERMISSION_DENIED",
                "reason": "authenticated account identity does not match expected account",
            }
        )
        return result

    # Authentication is proven. Publish/media entitlement is not. Do not promote
    # provider health to READY merely because /2/users/me succeeded.
    result.update(
        {
            "status": "UNKNOWN",
            "reason": (
                "identity authentication succeeded; write/media entitlement "
                "remains unproven without a publication side effect"
            ),
        }
    )
    return result
