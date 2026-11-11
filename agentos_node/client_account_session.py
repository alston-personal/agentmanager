"""Transport-neutral AgentOS client account session boundary.

A Node is a carrier, not the user's AgentOS identity. The trusted Bridge
must supply backend-authorized pairing, redemption, membership and revocation.
Nothing in this module implements OAuth or treats Node realm as user realm.
No credentials may be given to the game-facing projection.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_SESSION_RE = re.compile(r"^[a-zA-Z0-9._:-]{12,128}$")
_REALM_RE = re.compile(r"^(?:realm-u-[0-9a-f]{24}|realm-[a-z0-9][a-z0-9-]{0,63})$")
_DISPLAY_RE = re.compile(r"^[A-Za-z0-9@._+-]{1,128}$")


class AccountSessionBoundary:
    """A single Addon-scoped identity, independent of Node credentials.

    Callback trust assumptions:
    * `start_pairing` authorizes an external browser/device flow.
    * `redeem_pairing` returns an already server-verified subject plus
      session handle (not a raw OAuth access token).
    * `check_membership` checks server-side membership for that handle.
    * `revoke` invalidates the scoped handle on the authority.
    """

    def __init__(
        self,
        start_pairing: Callable[[], dict[str, Any]],
        redeem_pairing: Callable[[str], dict[str, Any]],
        check_membership: Callable[[str, str], bool],
        revoke: Callable[[str], bool],
    ):
        if not all(callable(fn) for fn in (start_pairing, redeem_pairing, check_membership, revoke)):
            raise TypeError("trusted_backend_callbacks_required")
        self._start = start_pairing
        self._redeem = redeem_pairing
        self._member = check_membership
        self._revoke = revoke
        self._ticket: str | None = None
        self._handle: str | None = None
        self._display: str | None = None
        self._realm: str | None = None

    def public_status(self) -> dict[str, Any]:
        # Game receives no Node credentials, OAuth token, pairing token or session handle.
        return {
            "signed_in": self._handle is not None,
            "account": self._display if self._handle else None,
            "realm": self._realm if self._handle else None,
        }

    def begin_login(self) -> dict[str, Any]:
        if self._handle is not None:
            return {"status": "ALREADY_SIGNED_IN"}
        # Pairing URL and private device secret must never be sent through Lua.
        result = self._start()
        if not isinstance(result, dict) or not _SESSION_RE.fullmatch(str(result.get("ticket", ""))):
            raise ValueError("untrusted_pairing_response")
        if set(result) != {"ticket"}:
            raise ValueError("pairing_must_remain_host_side")
        self._ticket = result["ticket"]
        return {"status": "PAIRING_STARTED"}

    def complete_login(self, ticket: str) -> dict[str, Any]:
        if self._handle is not None:
            return {"status": "ALREADY_SIGNED_IN"}
        if not isinstance(ticket, str) or ticket != self._ticket:
            return {"status": "UNAUTHORIZED"}
        self._ticket = None  # one-shot even when provider denies or fails
        result = self._redeem(ticket)
        if not isinstance(result, dict) or set(result) != {"handle", "account"}:
            raise ValueError("untrusted_identity_response")
        handle, account = result["handle"], result["account"]
        if not isinstance(handle, str) or not _SESSION_RE.fullmatch(handle):
            raise ValueError("invalid_session_handle")
        if not isinstance(account, str) or not _DISPLAY_RE.fullmatch(account):
            raise ValueError("invalid_public_identity")
        self._handle, self._display, self._realm = handle, account, None
        return {"status": "SIGNED_IN"}

    def choose_realm(self, realm: str) -> dict[str, Any]:
        if not self._handle:
            return {"status": "SIGN_IN_REQUIRED"}
        if not isinstance(realm, str) or not _REALM_RE.fullmatch(realm):
            return {"status": "INVALID_REALM"}
        # Fail closed: a Node connection is NOT evidence of user membership.
        self._realm = None
        try:
            permitted = self._member(self._handle, realm)
        except Exception:
            return {"status": "AUTH_UNAVAILABLE"}
        if permitted is not True:
            return {"status": "REALM_FORBIDDEN"}
        self._realm = realm
        return {"status": "REALM_SELECTED"}

    def sign_out(self) -> dict[str, Any]:
        handle = self._handle
        self._ticket = self._handle = self._display = self._realm = None
        if handle is None:
            return {"status": "SIGNED_OUT"}
        try:
            revoked = self._revoke(handle)
        except Exception:
            revoked = False
        # Local session is discarded regardless; failed backend revocation
        # must be reported, not falsely claimed completed.
        return {"status": "SIGNED_OUT" if revoked is True else "REVOCATION_UNCONFIRMED"}
