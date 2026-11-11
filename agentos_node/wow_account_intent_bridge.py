"""Host-only WoW account-intent dispatcher for the existing AgentOS Windows Node.

This is an integration contract, NOT a resident Bridge or OAuth endpoint.
The caller must inject trusted ONE identity callbacks and an independently
attested capture authorization probe. Node enrollment is never changed.
"""
from __future__ import annotations

from typing import Any

from agentos_node.client_account_session import AccountSessionBoundary
from agentos_node.wow_bridge_protocol import NodeBoundAccountGateway
from agentos_node.wow_browser_pairing_client import HostBrowserPairingProvider


class WoWAccountIntentBridge:
    def __init__(self, *, account: AccountSessionBoundary, capture_authorized, browser_provider=None):
        if not isinstance(account, AccountSessionBoundary):
            raise TypeError("verified_account_session_required")
        if not callable(capture_authorized):
            raise TypeError("capture_authorization_required")
        self._account = account
        self._browser_provider = browser_provider
        self._capture_authorized = capture_authorized
        self._gateway = NodeBoundAccountGateway(capture_authorized, self._handle)

    @classmethod
    def with_agentos_browser(cls, *, capture_authorized, post=None, open_browser=None):
        """Use existing AgentOS OAuth browser session, not Node credentials."""
        options = {}
        if post is not None:
            options["post"] = post
        if open_browser is not None:
            options["open_browser"] = open_browser
        provider = HostBrowserPairingProvider(**options)
        account = AccountSessionBoundary(
            provider.start_pairing,
            provider.redeem_pairing,
            provider.check_membership,
            provider.revoke,
        )
        return cls(account=account, capture_authorized=capture_authorized, browser_provider=provider)

    def poll_browser_login(self) -> dict[str, str]:
        """Trusted host periodic callback, never invoked by Lua game packet.

        Server proof must exist BEFORE consuming the one-shot account ticket.
        """
        if self._capture_authorized() is not True:
            return {"status": "BRIDGE_NOT_AUTHORIZED"}
        provider = self._browser_provider
        if provider is None or provider.pairing_ticket() is None:
            return {"status": "PAIRING_NOT_STARTED"}
        if not provider.check_ready():
            return {"status": "PAIRING_PENDING"}
        ticket = provider.pairing_ticket()
        result = self._account.complete_login(ticket)
        if result.get("status") != "SIGNED_IN":
            return {"status": "LOGIN_UNAVAILABLE"}
        realm = provider.authorized_realm()
        if not realm or self._account.choose_realm(realm).get("status") != "REALM_SELECTED":
            self._account.sign_out()
            return {"status": "REALM_FORBIDDEN"}
        return {"status": "SIGNED_IN"}

    def _handle(self, action: str) -> dict[str, str]:
        if action == "wow.account.login.start":
            result = self._account.begin_login()
        elif action == "wow.account.logout":
            result = self._account.sign_out()
        else:
            raise ValueError("unsupported_account_intent")
        # No pairing ticket, URL, Realm, OAuth state, or session handle.
        return {"status": str(result["status"])}

    def accept_capture(self, cells: list[int]) -> dict[str, Any]:
        return self._gateway.accept(cells)

    def public_account(self) -> dict[str, Any]:
        # Not itself a game transport. The real host must authenticate and
        # correlate any outbound display projection to a verified game session.
        return self._account.public_status()
