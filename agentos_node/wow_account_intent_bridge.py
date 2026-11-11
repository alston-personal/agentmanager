"""Host-only WoW account-intent dispatcher for the existing AgentOS Windows Node.

This is an integration contract, NOT a resident Bridge or OAuth endpoint.
The caller must inject trusted ONE identity callbacks and an independently
attested capture authorization probe. Node enrollment is never changed.
"""
from __future__ import annotations

from typing import Any

from agentos_node.client_account_session import AccountSessionBoundary
from agentos_node.wow_bridge_protocol import NodeBoundAccountGateway


class WoWAccountIntentBridge:
    def __init__(self, *, account: AccountSessionBoundary, capture_authorized):
        if not isinstance(account, AccountSessionBoundary):
            raise TypeError("verified_account_session_required")
        if not callable(capture_authorized):
            raise TypeError("capture_authorization_required")
        self._account = account
        self._gateway = NodeBoundAccountGateway(capture_authorized, self._handle)

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
