from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .contracts import SocialRequest, receipt_for, utc_now
from .credentials import AccountBinding, CredentialVault
from .governance import RuntimeWriteAcceptance, SocialWriteGate
from .oauth import OAuthStateStore

THREADS_SCOPES = ("threads_basic", "threads_content_publish", "threads_read_replies", "threads_manage_replies", "threads_keyword_search")
THREADS_TEXT_LIMIT = 500
THREADS_ATTACHMENT_LIMIT = 10000
THREADS_READ_PAGE_LIMIT = 3
THREADS_READ_ITEM_LIMIT = 150
THREAD_FIELDS = "id,text,timestamp,username,permalink,is_quote_post,has_replies"
REPLY_FIELDS = "id,text,timestamp,username,permalink,is_quote_post,has_replies,is_reply,is_reply_owned_by_me,root_post,replied_to"


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
    """Official Threads transport; provider credentials remain inside shared runtime."""

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
        query = urllib.parse.urlencode({"client_id": config.app_id, "redirect_uri": config.redirect_uri, "scope": ",".join(THREADS_SCOPES), "response_type": "code", "state": state})
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
        except urllib.error.HTTPError as exc:
            safe_code = f"http_{int(exc.code)}"
            provider_code = ""
            provider_type = ""
            try:
                raw = exc.read().decode("utf-8", "replace")
                body = json.loads(raw)
                err = body.get("error") if isinstance(body, dict) else None
                if isinstance(err, dict):
                    provider_code = str(err.get("code") or "")
                    provider_type = str(err.get("type") or "")
            except Exception:
                pass
            detail = "_".join(part for part in (safe_code, provider_type, provider_code) if part)
            raise ThreadsProviderError(f"threads_api_unavailable_{detail}") from exc
        except Exception as exc:
            raise ThreadsProviderError("threads_api_unavailable_transport") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            err = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(err, dict):
                code = str(err.get("code") or "")
                etype = str(err.get("type") or "")
                detail = "_".join(part for part in (etype, code) if part)
                raise ThreadsProviderError(f"threads_api_rejected_{detail}" if detail else "threads_api_rejected")
            raise ThreadsProviderError("threads_api_rejected")
        return payload

    def exchange_code(self, code: str) -> str:
        config = self.config()
        short = self._request_json(f"{config.graph_host.rstrip('/')}/oauth/access_token", method="POST", body={"client_id": config.app_id, "client_secret": config.app_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": config.redirect_uri})
        short_token = str(short.get("access_token") or "")
        if not short_token:
            raise ThreadsProviderError("threads_token_missing")
        exchange = f"{config.graph_host.rstrip('/')}/access_token?" + urllib.parse.urlencode({"grant_type": "th_exchange_token", "client_secret": config.app_secret, "access_token": short_token})
        try:
            long_lived = self._request_json(exchange)
            return str(long_lived.get("access_token") or short_token)
        except ThreadsProviderError:
            return short_token

    def api(self, path: str, *, token: str, method: str = "GET", params: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.config()
        url = f"{config.graph_host.rstrip('/')}/{path.lstrip('/')}"
        params = dict(params or {})
        if method == "GET" and params:
            url += "?" + urllib.parse.urlencode(params)
            return self._request_json(url, token=token)
        return self._request_json(url, method=method, token=token, body=params)

    def paged(self, path: str, *, token: str, params: dict[str, Any], max_pages: int = THREADS_READ_PAGE_LIMIT) -> list[dict[str, Any]]:
        payload = self.api(path, token=token, params=params)
        rows: list[dict[str, Any]] = []
        pages = 0
        while True:
            pages += 1
            data = payload.get("data")
            if isinstance(data, list):
                rows.extend(item for item in data if isinstance(item, dict))
            if pages >= max_pages or len(rows) >= THREADS_READ_ITEM_LIMIT:
                break
            paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
            next_url = str(paging.get("next") or "")
            if not next_url:
                break
            payload = self._request_json(next_url, token=token)
        return rows[:THREADS_READ_ITEM_LIMIT]

    def identity(self, token: str) -> dict[str, Any]:
        return self.api("me", token=token, params={"fields": "id,username,name,threads_profile_picture_url"})

    def revoke(self, token: str) -> None:
        # Local disconnect is mandatory. Remote revocation may be supplied when provider policy allows it.
        return None


class ThreadsCapability:
    def __init__(self, vault: CredentialVault, transport: ThreadsProviderTransport, oauth_states: OAuthStateStore | None = None, write_gate: SocialWriteGate | None = None) -> None:
        self.vault = vault
        self.transport = transport
        self.oauth_states = oauth_states or OAuthStateStore()
        self.write_gate = write_gate or SocialWriteGate()

    def _configured(self) -> bool:
        try:
            return self.transport.config().configured
        except ThreadsProviderError:
            return False

    def _read_binding(self, request: SocialRequest) -> tuple[AccountBinding | None, str | None]:
        if not request.account_binding_id:
            return None, "account_binding_required"
        binding = self.vault.get_binding(request.account_binding_id)
        if binding is None or binding.product_id != request.product_id or binding.platform != "threads":
            return None, "account_binding_mismatch"
        return binding, None

    @staticmethod
    def _safe_media(item: dict[str, Any]) -> dict[str, Any]:
        def ref(name: str) -> dict[str, str] | None:
            raw = item.get(name)
            if isinstance(raw, dict) and raw.get("id"):
                return {"id": str(raw["id"])}
            return None
        return {
            "id": str(item.get("id") or ""),
            "text": str(item.get("text") or "")[:12000],
            "timestamp": item.get("timestamp"),
            "username": item.get("username"),
            "permalink": item.get("permalink"),
            "is_quote_post": bool(item.get("is_quote_post", False)),
            "has_replies": bool(item.get("has_replies", False)),
            "is_reply": bool(item.get("is_reply", False)),
            "is_reply_owned_by_me": bool(item.get("is_reply_owned_by_me", False)),
            "root_post": ref("root_post"),
            "replied_to": ref("replied_to"),
        }

    def read(self, request: SocialRequest) -> dict[str, Any]:
        request.validate()
        started = utc_now()
        binding, error = self._read_binding(request)
        if error or binding is None:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code=error or "account_binding_required").to_dict()
        try:
            token = self.vault.get_access_token(binding.binding_id)
            if request.operation == "identity.read":
                identity = self.transport.identity(token)
                safe = {
                    "provider_account_id": str(identity.get("id") or binding.provider_account_id),
                    "username": identity.get("username") or binding.username,
                    "name": identity.get("name"),
                    "profile_picture_url": identity.get("threads_profile_picture_url"),
                }
                return receipt_for(request, started_at=started, ok=True, capability="social.threads.identity.read", result={"identity": safe}).to_dict()
            if request.operation == "post.read":
                rows = self.transport.paged("me/threads", token=token, params={"fields": THREAD_FIELDS, "limit": 50})
                return receipt_for(request, started_at=started, ok=True, capability="social.threads.post.read", result={"items": [self._safe_media(row) for row in rows], "truncated": len(rows) >= THREADS_READ_ITEM_LIMIT}).to_dict()
            if request.operation == "keyword.search":
                rows = self.transport.paged("keyword_search", token=token, params={
                    "q": str(request.query or "").strip(),
                    "search_type": str(request.search_type or "RECENT").upper(),
                    "search_mode": str(request.search_mode or "KEYWORD").upper(),
                    "fields": THREAD_FIELDS,
                    "limit": 50,
                }, max_pages=1)
                return receipt_for(request, started_at=started, ok=True, capability="social.threads.keyword.search", result={"items": [self._safe_media(row) for row in rows], "truncated": len(rows) >= 50}).to_dict()
            if request.operation == "replies.read":
                object_id = str(request.object_id or "").strip()
                if not object_id:
                    return receipt_for(request, started_at=started, ok=False, capability="social.threads.replies.read", error_code="thread_object_id_required").to_dict()
                rows = self.transport.paged(f"{object_id}/conversation", token=token, params={"fields": REPLY_FIELDS, "reverse": "false", "limit": 100})
                return receipt_for(request, started_at=started, ok=True, capability="social.threads.replies.read", platform_object_id=object_id, result={"items": [self._safe_media(row) for row in rows], "truncated": len(rows) >= THREADS_READ_ITEM_LIMIT}).to_dict()
            raise ValueError("unsupported_threads_read_operation")
        except ThreadsProviderError as exc:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code=str(exc)).to_dict()

    def status(self, request: SocialRequest) -> dict[str, Any]:
        request.validate()
        if request.operation in {"identity.read", "post.read", "replies.read", "keyword.search"}:
            return self.read(request)
        if request.operation != "status":
            raise ValueError("status_or_read_operation_required")
        binding = self.vault.get_binding(request.account_binding_id) if request.account_binding_id else None
        if binding is not None and (binding.product_id != request.product_id or binding.platform != "threads"):
            binding = None
        return {"schema": "agentos.social-status/v1", "product_id": request.product_id, "platform": "threads", "configured": self._configured(), "connected": binding is not None, "account": ({"binding_id": binding.binding_id, "provider_account_id": binding.provider_account_id, "username": binding.username} if binding else None)}

    def begin_connect(self, request: SocialRequest, *, browser_session_id: str) -> dict[str, str]:
        request.validate()
        if request.operation != "connect":
            raise ValueError("connect_operation_required")
        state = self.oauth_states.issue(product_id=request.product_id, browser_session_id=browser_session_id, platform="threads", return_to=request.return_to or "/")
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
        primary = str(request.primary_text or "").strip()
        if not primary or len(primary) > THREADS_TEXT_LIMIT:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code="threads_primary_text_invalid").to_dict()
        params: dict[str, Any] = {"media_type": "TEXT", "text": primary}
        if request.operation != "reply":
            params["auto_publish_text"] = "true"
        attachment = request.text_attachment
        if attachment:
            plaintext = str(attachment.get("plaintext") or "").strip()
            if not plaintext or len(plaintext) > THREADS_ATTACHMENT_LIMIT:
                return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code="threads_text_attachment_invalid").to_dict()
            sanitized: dict[str, str] = {"plaintext": plaintext}
            link = str(attachment.get("link_attachment_url") or "").strip()
            if link:
                parsed = urllib.parse.urlsplit(link)
                if parsed.scheme not in {"http", "https"}:
                    return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code="threads_text_attachment_link_invalid").to_dict()
                sanitized["link_attachment_url"] = link
            params["text_attachment"] = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
        if request.operation == "reply":
            params["reply_to_id"] = request.reply_to_id
        token = self.vault.get_access_token(binding.binding_id)
        try:
            created = self.transport.api("me/threads", token=token, method="POST", params=params)
            creation_id = str(created.get("id") or "")
            if not creation_id:
                raise ThreadsProviderError("threads_publish_id_missing")
            if request.operation == "reply":
                published = self.transport.api(
                    "me/threads_publish",
                    token=token,
                    method="POST",
                    params={"creation_id": creation_id},
                )
                thread_id = str(published.get("id") or "")
                if not thread_id:
                    raise ThreadsProviderError("threads_publish_id_missing")
            else:
                thread_id = creation_id
            return receipt_for(request, started_at=started, ok=True, capability=f"social.threads.{request.operation}", platform_object_id=thread_id).to_dict()
        except ThreadsProviderError as exc:
            return receipt_for(request, started_at=started, ok=False, capability=f"social.threads.{request.operation}", error_code=str(exc)).to_dict()
