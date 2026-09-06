from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthState:
    state: str
    product_id: str
    browser_session_id: str
    platform: str
    return_to: str
    expires_at: float


class OAuthStateStore:
    """Single-use, product-scoped OAuth state. Provider codes/tokens never enter return URLs."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._states: dict[str, OAuthState] = {}

    @staticmethod
    def safe_return_to(value: str | None) -> str:
        route = str(value or "/").strip()
        if not route.startswith("/") or route.startswith("//"):
            raise ValueError("unsafe_oauth_return_route")
        return route[:1024]

    def issue(self, *, product_id: str, browser_session_id: str, platform: str, return_to: str = "/") -> OAuthState:
        if not product_id or not browser_session_id:
            raise ValueError("oauth_product_and_session_required")
        now = time.time()
        self._states = {key: item for key, item in self._states.items() if item.expires_at > now}
        state = OAuthState(
            state=secrets.token_urlsafe(32),
            product_id=product_id,
            browser_session_id=browser_session_id,
            platform=platform,
            return_to=self.safe_return_to(return_to),
            expires_at=now + self.ttl_seconds,
        )
        self._states[state.state] = state
        return state

    def consume(self, *, state: str, product_id: str, browser_session_id: str, platform: str) -> OAuthState:
        item = self._states.pop(str(state or ""), None)
        if item is None or item.expires_at <= time.time():
            raise PermissionError("oauth_state_invalid_or_expired")
        if (item.product_id, item.browser_session_id, item.platform) != (product_id, browser_session_id, platform):
            raise PermissionError("oauth_state_scope_mismatch")
        return item


def sanitized_oauth_return(route: str, *, connected: bool, binding_id: str | None = None) -> str:
    """Return only local routing state; never include provider code/token/credential URLs."""
    route = OAuthStateStore.safe_return_to(route)
    suffix = "social=connected" if connected else "social=disconnected"
    if binding_id:
        suffix += "&binding=" + binding_id.replace("&", "").replace("=", "")[:128]
    return route + ("&" if "?" in route else "?") + suffix
