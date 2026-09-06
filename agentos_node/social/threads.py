from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .contracts import SocialRequest, receipt_for, utc_now
from .credentials import AccountBinding, CredentialVault
from .governance import RuntimeWriteAcceptance, SocialWriteGate
from .oauth import OAuthStateStore

THREADS_SCOPES = ("threads_basic", "threads_content_publish")
THREADS_TEXT_LIMIT = 500
THREADS_ATTACHMENT_LIMIT = 10000


class ThreadsProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThreadsProviderConfig:
    app_id: str
    app_secret: str
    redirect_uri: str
    graph_host: str = "https://graph.threads.net"
    authorize_host: str = "https://threads.net"

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret and self.redirect_uri)


class ThreadsProviderTransport:
    """Official Threads provider transport. Secrets remain inside the shared runtime."""

    def __init__(self, config_loader: Callable[[], ThreadsProviderConfig], timeout: float = 15.0) -> None:
        self._config_loader = config_loader
        self.timeout = timeout

    def config(self) -> ThreadsProviderConfig:
        config = self._config_loader()
        if not config.configured:
            raise ThreadsProviderError("threads_oauth_not_configured")
        return config

    def authorization_url(self, state: str) -> str:
        config = self.config()
        query = urllib.parse.urlencode({
            "client_id": config.app_id,
            "redirect_uri": config.redirect_uri,
            "scope": ",".join(THREADS_SCOPES),
            "response_type": "code",
            "state": state,
        })
        return f"{config.authorize_host.rstrip('/')}/oauth/authorize?{query}"

    def _request_json(self, url: str, *, method: str = "GET", token: str | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "AgentOS-Social/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urllib.parse.urlencode(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ThreadsProviderError("threads_api_unavailable") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise ThreadsProviderError("threads_api_rejected")
        return payload

    def exchange_code(self, code: str) -> str:
        config = self.config()
        payload = self._request_json(
            f"{config.graph_host.rstrip('/')}/oauth/access_token",
            method="POST",
            body={"client_id": config.app_id, "client_secret": config.app_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": config.redirect_uri},
        )
        token = str(payload.get("access_token") or "")
        if not token:
            raise ThreadsProviderError("threads_token_missing")
        return token

    def api(self, path: str, *, token: str, method: str = "GET", params: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.config()
        url = f"{config.graph_host.rstrip('/')}/v1.0/{path.lstrip('/')}"
        params = dict(params or {})
        if method == "GET" and params:
            url += "?" + urllib.parse.urlencode(params)
            return self._request_json(url, token=token)
        return self._request_json(url, method=method, token=token, body=params)

    def identity(self, token: str) -> dict[str, Any]:
        return self.api("me", token=token, params={"fields": "id,username"})

    def revoke(self, token: str) -> None:
        # Provider revocation endpoints/policies can change; runtime may supply a transport override.
        # Local disconnect is always performed even when remote revocation is unavailable.
        return None


class ThreadsCapability:
    def __init__(self, vault: CredentialVault, transport: ThreadsProviderTransport, oauth_states: OAuthStateStore | None = None, write_gate: SocialWriteGate | None = None) -> None:
        self.vault = vault
        self.transport = transport
        self.oauth_states = oauth_states or OAuthStateStore()
        self.write_gate = write_gate or SocialWriteGate()

    def status(self, request: SocialRequest) -> dict[str, Any]:
        request.validate()
        binding = self.vault.get_binding(request.account_binding_id) if request.account_binding_id else None
        return {"schema": "agentos.social-status/v1", "product_id": request.product_id, "platform": "threads", "configured": self.transport.config().configured if self._configured() else False, "connected": binding is not None, "account": ({"binding_id": binding.binding_id, "provider_account_id": binding.provider_account_id, "username": binding.username} if binding else None)}

    def _configured(self) -> bool:
        try:
            return self.transport.config().configured
        except ThreadsProviderError:
            return False

    def begin_connect(self, request: SocialRequest, *, browser_session_id: str) -> dict[str, str]:
        request.validate()
        if request.operation != "connect":
            raise ValueError("connect_operation_required")
        state = self.oauth_states.issue(product_id=request.product_id, browser_session_id=browser_session_id, platform="threads", return_to=request.return_to or "/")
        # This transient response is intentionally not a SocialReceipt. It contains no app secret/token/code.
        return {"schema": "agentos.social-oauth-redirect/v1", "authorization_url": self.transport.authorization_url(state.state), "state": state.state}

    def complete_connect(self, *, product_id: str, browser_session_id: str, state: str, code: str) -> dict[str, Any]:
        oauth = self.oauth_states.consume(state=state, product_id=product_id, browser_session_id=browser_session_id, platform="threads")
        token = self.transport.exchange_code(code)
        identity = self.transport.identity(token)
        account_id = str(identity.get("id") or "")
        if not account_id:
            raise ThreadsProviderError("threads_identity_missing")
        binding_id = f"{product_id}:threads:{account_id}"
        self.vault.bind(AccountBinding(binding_id, product_id, "threads", account_id, str(identity.get("username") or "") or None), token)
        return {"schema": "agentos.social-oauth-complete/v1", "connected": True, "binding_id": binding_id, "account": {"provider_account_id": account_id, "username": identity.get("username")}, "return_to": oauth.return_to}

    def disconnect(self, request: SocialRequest, *, acceptance: RuntimeWriteAcceptance | None = None) -> dict[str, Any]:
        started = utc_now()
        self.write_gate.authorize(request, acceptance)
        if not request.account_binding_id:
            return receipt_for(request, started_at=started, ok=False, capability="social.threads.disconnect", error_code="account_binding_required").to_dict()
        try:
            token = self.vault.get_access_token(request.account_binding_id)
            try:
                self.transport.revoke(token)
            finally:
                self.vault.disconnect(request.account_binding_id)
            return receipt_for(request, started_at=started, ok=True, capability="social.threads.disconnect").to_dict()
        except Exception:
            self.vault.disconnect(request.account_binding_id)
            return receipt_for(request, started_at=started, ok=True, capability="social.threads.disconnect", result={"remote_revocation": "unconfirmed"}).to_dict()

    def publish(self, request: SocialRequest, *, acceptance: RuntimeWriteAcceptance | None = None) -> dict[str, Any]:
        started = utc_now()
        self.write_gate.authorize(request, acceptance)
        binding = self.vault.get_binding(request.account_binding_id or "")
        if binding is None or binding.product_id != request.product_id or binding.provider_account_id != request.target_account_id:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code="account_binding_mismatch").to_dict()
        primary = str(request.primary_text or "")
        attachment = str(request.text_attachment or "")
        if len(primary) > THREADS_TEXT_LIMIT or len(attachment) > THREADS_ATTACHMENT_LIMIT:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code="threads_content_limit_exceeded").to_dict()
        token = self.vault.get_access_token(binding.binding_id)
        params: dict[str, Any] = {"media_type": "TEXT", "text": primary}
        if attachment:
            params["text_attachment"] = attachment
            params["auto_publish_text"] = "true"
        if request.operation == "reply":
            params["reply_to_id"] = request.reply_to_id
        try:
            created = self.transport.api(f"{binding.provider_account_id}/threads", token=token, method="POST", params=params)
            creation_id = str(created.get("id") or "")
            if not creation_id:
                raise ThreadsProviderError("threads_creation_id_missing")
            if attachment:
                thread_id = creation_id
            else:
                published = self.transport.api(f"{binding.provider_account_id}/threads_publish", token=token, method="POST", params={"creation_id": creation_id})
                thread_id = str(published.get("id") or "")
            if not thread_id:
                raise ThreadsProviderError("threads_publish_id_missing")
            return receipt_for(request, started_at=started, ok=True, capability=f"social.threads.{request.operation}", platform_object_id=thread_id).to_dict()
        except ThreadsProviderError as exc:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code=str(exc)).to_dict()
