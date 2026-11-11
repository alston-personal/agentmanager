"""Real HTTPS account-pairing client for a trusted Windows WoW Bridge.

Reuses the existing AgentOS browser OAuth/site session, never signs in using
Node credentials. NOT an autonomous capture daemon or addon transport.
The server-side endpoints must be deployed before this can work.
"""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
import webbrowser
from typing import Any
from urllib.parse import urlparse

ORIGIN = "https://agentos.milkcat.org"
_MAX_BYTES = 4096


class PairingUnavailable(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PairingUnavailable("unexpected_redirect")


def _post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    if endpoint not in {"start", "poll", "revoke"}:
        raise ValueError("unsupported_pairing_endpoint")
    url = ORIGIN + "/v1/wow/account/" + endpoint
    wire = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=wire, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "AgentOS-WoW-HostBridge/0.1",
    }, method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=10) as response:
            if response.status not in {200, 201}:
                raise PairingUnavailable("pairing_http_denied")
            data = response.read(_MAX_BYTES + 1)
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise PairingUnavailable("agentos_pairing_unavailable") from exc
    if len(data) > _MAX_BYTES:
        raise PairingUnavailable("oversized_pairing_response")
    try:
        result = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise PairingUnavailable("invalid_pairing_response") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise PairingUnavailable("pairing_rejected")
    return result


def _check_browser_url(url: str, code: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.netloc == "agentos.milkcat.org"
        and parsed.path == "/wow/account/authorize" and parsed.query == "code=" + code
        and not parsed.fragment)


class HostBrowserPairingProvider:
    """Callbacks for AccountSessionBoundary; carries its own host-only secret.

    The host must separately attest the active WoW window before invoking
    login.start or logout. Never forward ticket/secret to pixel reply slots.
    """

    def __init__(self, *, post=_post, open_browser=webbrowser.open):
        self._post = post
        self._open_browser = open_browser
        self._code: str | None = None
        self._secret: str | None = None
        self._approved: dict[str, str] | None = None
        self._handle: str | None = None

    def start_pairing(self) -> dict[str, str]:
        if self._code is not None:
            raise PairingUnavailable("pairing_already_active")
        response = self._post("start", {})
        code, secret, url = response.get("code"), response.get("claim_secret"), response.get("verification_url")
        if not (isinstance(code, str) and len(code) == 12 and
                isinstance(secret, str) and len(secret) == 64 and
                isinstance(url, str) and _check_browser_url(url, code)):
            raise PairingUnavailable("unsafe_pairing_url_or_claim")
        # Keep the device claim on the host; never return it to the game.
        self._code, self._secret = code, secret
        try:
            if self._open_browser(url) is not True:
                raise PairingUnavailable("browser_open_not_confirmed")
        except Exception as exc:
            self._code = self._secret = None
            raise PairingUnavailable("browser_open_failed") from exc
        return {"ticket": code}

    def pairing_ticket(self) -> str | None:
        return self._code

    def check_ready(self) -> bool:
        if not self._code or not self._secret:
            return False
        response = self._post("poll", {"code": self._code, "claim_secret": self._secret})
        if response.get("state") == "pending":
            return False
        if response.get("state") != "approved":
            raise PairingUnavailable("pairing_not_approved")
        account, realm = response.get("account"), response.get("realm")
        if not isinstance(account, str) or not isinstance(realm, str):
            raise PairingUnavailable("invalid_account_projection")
        self._approved = {"account": account, "realm": realm}
        return True

    def redeem_pairing(self, ticket: str) -> dict[str, str]:
        if ticket != self._code or not self.check_ready() or self._approved is None:
            raise PairingUnavailable("pairing_not_ready")
        self._handle = "wowhost-" + secrets.token_hex(16)
        return {"handle": self._handle, "account": self._approved["account"]}

    def check_membership(self, handle: str, realm: str) -> bool:
        # The server checked Realm ownership at browser approval; this is a
        # display projection, not permission to issue ONE tasks.
        return handle == self._handle and self._approved is not None and self._approved["realm"] == realm

    def authorized_realm(self) -> str | None:
        return self._approved["realm"] if self._approved else None

    def revoke(self, handle: str) -> bool:
        if handle != self._handle or not self._code or not self._secret:
            return False
        try:
            result = self._post("revoke", {"code": self._code, "claim_secret": self._secret})
            return result.get("state") == "revoked"
        except PairingUnavailable:
            return False
        finally:
            self._code = self._secret = self._approved = self._handle = None

    def reset_unpaired(self) -> None:
        # Call only after failed/expired unpaired login; never during signed-in
        # session, to avoid silently orphaning an active server pairing.
        if self._handle is not None:
            raise PairingUnavailable("signed_in_revoke_first")
        self._code = self._secret = self._approved = None
