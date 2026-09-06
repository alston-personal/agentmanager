from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any

from .contracts import SocialRequest
from .oauth import sanitized_oauth_return
from .provider_callbacks import ThreadsLifecycleCallbacks
from .runtime_storage import FileCredentialVault, OneShotAcceptanceStore
from .threads import ThreadsCapability, ThreadsProviderConfig, ThreadsProviderTransport

MAX_BODY = 64 * 1024
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
DEFAULT_CREDENTIAL_PATH = Path("/home/ubuntu/agent-data/runtime/social/credentials.json")
DEFAULT_PUBLIC_BASE = "https://studio.milkcat.org/dashboard/api/social"
SESSION_COOKIE = "agentos_social_session"
BROWSER_HANDOFF_TTL_SECONDS = 300
CONNECTION_RESULT_TTL_SECONDS = 600


@dataclass(frozen=True)
class ProductRegistration:
    product_id: str
    api_key: str
    return_base: str


class ProductRegistry:
    def __init__(self, registrations: dict[str, ProductRegistration]) -> None:
        self._items = registrations

    @classmethod
    def from_env(cls) -> "ProductRegistry":
        raw = os.environ.get("AGENTOS_SOCIAL_PRODUCTS_JSON", "{}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("social_product_registry_invalid") from exc
        if not isinstance(value, dict):
            raise RuntimeError("social_product_registry_invalid")
        items: dict[str, ProductRegistration] = {}
        for product_id, item in value.items():
            if not isinstance(item, dict):
                raise RuntimeError("social_product_registry_invalid")
            api_key = str(item.get("api_key") or "")
            return_base = str(item.get("return_base") or "").rstrip("/")
            parsed = urllib.parse.urlsplit(return_base)
            if not product_id or not api_key or parsed.scheme not in {"https", "http"} or not parsed.netloc:
                raise RuntimeError("social_product_registry_invalid")
            items[str(product_id)] = ProductRegistration(str(product_id), api_key, return_base)
        return cls(items)

    def registration(self, product_id: str) -> ProductRegistration:
        item = self._items.get(product_id)
        if item is None:
            raise PermissionError("social_product_not_registered")
        return item

    def authenticate(self, product_id: str, supplied: str) -> ProductRegistration:
        item = self.registration(product_id)
        if not hmac.compare_digest(item.api_key, str(supplied or "")):
            raise PermissionError("social_product_auth_failed")
        return item


@dataclass(frozen=True)
class BrowserContext:
    product_id: str
    browser_session_id: str
    connection_id: str


class BrowserContextStore:
    """Short-lived in-process callback context. Restart fails closed."""

    def __init__(self) -> None:
        self._items: dict[str, BrowserContext] = {}
        self._lock = RLock()

    def bind(self, state: str, product_id: str, browser_session_id: str, connection_id: str) -> None:
        with self._lock:
            self._items[state] = BrowserContext(product_id, browser_session_id, connection_id)

    def consume(self, state: str, browser_session_id: str) -> BrowserContext:
        with self._lock:
            value = self._items.pop(state, None)
        if value is None:
            raise PermissionError("social_oauth_browser_context_invalid_or_consumed")
        if not hmac.compare_digest(value.browser_session_id, str(browser_session_id or "")):
            raise PermissionError("social_oauth_browser_session_mismatch")
        return value


@dataclass(frozen=True)
class BrowserHandoff:
    product_id: str
    platform: str
    return_to: str
    connection_id: str
    expires_at: float


class BrowserHandoffStore:
    """Opaque one-time bridge from authenticated product backend to the user's browser."""

    def __init__(self, ttl_seconds: int = BROWSER_HANDOFF_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, BrowserHandoff] = {}
        self._lock = RLock()

    def issue(self, *, product_id: str, platform: str, return_to: str, connection_id: str) -> str:
        now = time.time()
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._items = {key: item for key, item in self._items.items() if item.expires_at > now}
            self._items[ticket] = BrowserHandoff(
                product_id=product_id,
                platform=platform,
                return_to=return_to,
                connection_id=connection_id,
                expires_at=now + self.ttl_seconds,
            )
        return ticket

    def consume(self, ticket: str) -> BrowserHandoff:
        with self._lock:
            item = self._items.pop(str(ticket or ""), None)
        if item is None or item.expires_at <= time.time():
            raise PermissionError("social_browser_handoff_invalid_or_expired")
        return item


@dataclass(frozen=True)
class ConnectionResult:
    product_id: str
    platform: str
    binding_id: str
    account: dict[str, Any]
    expires_at: float


class ConnectionResultStore:
    """Secret-free single-consume OAuth completion result for the authenticated product backend."""

    def __init__(self, ttl_seconds: int = CONNECTION_RESULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, ConnectionResult] = {}
        self._lock = RLock()

    def new_connection_id(self) -> str:
        return secrets.token_urlsafe(24)

    def complete(self, connection_id: str, *, product_id: str, platform: str, binding_id: str, account: dict[str, Any]) -> None:
        if not connection_id or not binding_id:
            raise ValueError("social_connection_result_scope_required")
        safe_account = {
            "provider_account_id": str(account.get("provider_account_id") or ""),
            "username": (str(account.get("username")) if account.get("username") is not None else None),
        }
        with self._lock:
            self._items[connection_id] = ConnectionResult(
                product_id=product_id,
                platform=platform,
                binding_id=binding_id,
                account=safe_account,
                expires_at=time.time() + self.ttl_seconds,
            )

    def consume(self, connection_id: str, *, product_id: str, platform: str) -> dict[str, Any]:
        with self._lock:
            item = self._items.pop(str(connection_id or ""), None)
        if item is None or item.expires_at <= time.time():
            raise PermissionError("social_connection_result_invalid_or_expired")
        if (item.product_id, item.platform) != (product_id, platform):
            raise PermissionError("social_connection_result_scope_mismatch")
        return {
            "schema": "agentos.social-connection-result/v1",
            "connected": True,
            "binding_id": item.binding_id,
            "account": item.account,
        }


class SocialRuntime:
    def __init__(
        self,
        *,
        products: ProductRegistry,
        threads: ThreadsCapability,
        acceptances: OneShotAcceptanceStore | None = None,
        browser_contexts: BrowserContextStore | None = None,
        browser_handoffs: BrowserHandoffStore | None = None,
        connection_results: ConnectionResultStore | None = None,
        control_token: str = "",
        threads_lifecycle: ThreadsLifecycleCallbacks | None = None,
        public_base: str = DEFAULT_PUBLIC_BASE,
    ) -> None:
        self.products = products
        self.threads = threads
        self.acceptances = acceptances or OneShotAcceptanceStore()
        self.browser_contexts = browser_contexts or BrowserContextStore()
        self.browser_handoffs = browser_handoffs or BrowserHandoffStore()
        self.connection_results = connection_results or ConnectionResultStore()
        self.control_token = control_token
        self.threads_lifecycle = threads_lifecycle
        self.public_base = str(public_base or DEFAULT_PUBLIC_BASE).rstrip("/")

    @classmethod
    def from_env(cls, credential_path: str | Path = DEFAULT_CREDENTIAL_PATH) -> "SocialRuntime":
        products = ProductRegistry.from_env()
        vault = FileCredentialVault(credential_path)
        public_base = os.environ.get("AGENTOS_SOCIAL_PUBLIC_BASE", DEFAULT_PUBLIC_BASE)

        def config_loader() -> ThreadsProviderConfig:
            return ThreadsProviderConfig(
                app_id=os.environ.get("AGENTOS_THREADS_APP_ID", ""),
                app_secret=os.environ.get("AGENTOS_THREADS_APP_SECRET", ""),
                redirect_uri=os.environ.get("AGENTOS_THREADS_REDIRECT_URI", ""),
            )

        transport = ThreadsProviderTransport(config_loader)
        threads = ThreadsCapability(vault, transport)
        lifecycle = ThreadsLifecycleCallbacks(
            vault=vault,
            transport=transport,
            public_base=public_base,
        )
        return cls(
            products=products,
            threads=threads,
            control_token=os.environ.get("AGENTOS_SOCIAL_CONTROL_TOKEN", ""),
            threads_lifecycle=lifecycle,
            public_base=public_base,
        )

    def configured_status(self) -> dict[str, Any]:
        return {
            "schema": "agentos.social-runtime-status/v1",
            "service": "agentos-social-runtime",
            "threads": {"configured": self.threads._configured()},
        }

    def status(self, request: SocialRequest) -> dict[str, Any]:
        self.products.registration(request.product_id)
        if request.operation == "status" and request.object_id:
            return self.connection_results.consume(
                request.object_id,
                product_id=request.product_id,
                platform=request.platform,
            )
        return self.threads.status(request)

    def connect(self, request: SocialRequest) -> dict[str, Any]:
        """Create only a product-safe browser handoff; provider OAuth state stays runtime-side."""
        self.products.registration(request.product_id)
        if request.operation != "connect" or request.platform != "threads":
            raise ValueError("threads_connect_operation_required")
        connection_id = self.connection_results.new_connection_id()
        ticket = self.browser_handoffs.issue(
            product_id=request.product_id,
            platform=request.platform,
            return_to=str(request.return_to or "/"),
            connection_id=connection_id,
        )
        query = urllib.parse.urlencode({"ticket": ticket})
        return {
            "schema": "agentos.social-browser-handoff/v1",
            "browser_start_url": f"{self.public_base}/v1/social/oauth/threads/start?{query}",
            "connection_id": connection_id,
            "expires_in": self.browser_handoffs.ttl_seconds,
        }

    def begin_browser_connect(self, ticket: str) -> tuple[str, str]:
        handoff = self.browser_handoffs.consume(ticket)
        if handoff.platform != "threads":
            raise PermissionError("social_browser_handoff_platform_mismatch")
        self.products.registration(handoff.product_id)
        browser_session_id = secrets.token_urlsafe(24)
        request = SocialRequest(
            product_id=handoff.product_id,
            platform="threads",
            operation="connect",
            return_to=handoff.return_to,
        ).validate()
        value = self.threads.begin_connect(request, browser_session_id=browser_session_id)
        state = str(value.pop("state"))
        authorization_url = str(value.get("authorization_url") or "")
        if not authorization_url:
            raise RuntimeError("social_oauth_authorization_url_missing")
        self.browser_contexts.bind(state, handoff.product_id, browser_session_id, handoff.connection_id)
        return authorization_url, browser_session_id

    def complete_connect(self, *, state: str, code: str, browser_session_id: str) -> tuple[str, dict[str, Any]]:
        context = self.browser_contexts.consume(state, browser_session_id)
        registration = self.products.registration(context.product_id)
        result = self.threads.complete_connect(
            product_id=context.product_id,
            browser_session_id=context.browser_session_id,
            state=state,
            code=code,
        )
        binding_id = str(result.get("binding_id") or "")
        account = result.get("account") if isinstance(result.get("account"), dict) else {}
        self.connection_results.complete(
            context.connection_id,
            product_id=context.product_id,
            platform="threads",
            binding_id=binding_id,
            account=account,
        )
        relative = sanitized_oauth_return(
            str(result.get("return_to") or "/"),
            connected=True,
        )
        return registration.return_base + relative, {
            "schema": "agentos.social-oauth-complete/v1",
            "connected": True,
            "connection_id": context.connection_id,
        }

    def provider_deauthorize(self, signed_request: str) -> dict[str, Any]:
        if self.threads_lifecycle is None:
            raise RuntimeError("threads_lifecycle_callbacks_unavailable")
        return self.threads_lifecycle.deauthorize(signed_request)

    def provider_data_deletion(self, signed_request: str) -> dict[str, Any]:
        if self.threads_lifecycle is None:
            raise RuntimeError("threads_lifecycle_callbacks_unavailable")
        return self.threads_lifecycle.data_deletion(signed_request)

    def issue_acceptance(self, request: SocialRequest, supplied_control_token: str) -> dict[str, str]:
        if not self.control_token or not hmac.compare_digest(self.control_token, str(supplied_control_token or "")):
            raise PermissionError("social_runtime_control_auth_failed")
        self.products.registration(request.product_id)
        acceptance_id = self.acceptances.issue(request)
        return {"schema": "agentos.social-write-acceptance/v1", "acceptance_id": acceptance_id, "one_shot": "true"}

    def execute_write(self, request: SocialRequest, acceptance_id: str) -> dict[str, Any]:
        self.products.registration(request.product_id)
        acceptance = self.acceptances.consume(acceptance_id, request)
        if request.operation in {"publish", "reply"}:
            return self.threads.publish(request, acceptance=acceptance)
        if request.operation == "disconnect":
            return self.threads.disconnect(request, acceptance=acceptance)
        raise ValueError("unsupported_social_write_operation")


class SocialRuntimeHandler(BaseHTTPRequestHandler):
    runtime: SocialRuntime
    server_version = "AgentOSSocialRuntime/0.1"

    def _json(self, status: int, payload: dict[str, Any], *, session_cookie: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if session_cookie:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={session_cookie}; Path=/v1/social/oauth/threads/callback; HttpOnly; Secure; SameSite=Lax",
            )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, *, session_cookie: str | None = None) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        if session_cookie:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={session_cookie}; Path=/v1/social/oauth/threads/callback; HttpOnly; Secure; SameSite=Lax",
            )
        self.end_headers()

    def _raw_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request_body_size_invalid")
        return self.rfile.read(length)

    def _body(self) -> dict[str, Any]:
        value = json.loads(self._raw_body().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("json_object_required")
        return value

    def _signed_request(self) -> str:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        raw = self._raw_body().decode("utf-8")
        if content_type == "application/json":
            value = json.loads(raw)
            signed = value.get("signed_request") if isinstance(value, dict) else ""
        else:
            signed = (urllib.parse.parse_qs(raw, keep_blank_values=True).get("signed_request") or [""])[0]
        signed = str(signed or "")
        if not signed:
            raise ValueError("threads_signed_request_required")
        return signed

    def _request(self, body: dict[str, Any]) -> SocialRequest:
        allowed = {
            "schema", "product_id", "platform", "operation", "account_binding_id", "target_account_id",
            "primary_text", "text_attachment", "object_id", "reply_to_id", "return_to", "write_intent_id",
        }
        if set(body) - allowed:
            raise ValueError("unsupported_social_request_field")
        return SocialRequest(**body).validate()

    def _product_auth(self, request: SocialRequest) -> None:
        self.runtime.products.authenticate(request.product_id, self.headers.get("X-AgentOS-Product-Key", ""))

    def _browser_session_cookie(self) -> str:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/healthz":
            self._json(HTTPStatus.OK, self.runtime.configured_status())
            return
        if parsed.path == "/v1/social/webhooks/threads/data-deletion/status":
            code = str((urllib.parse.parse_qs(parsed.query).get("code") or [""])[0])
            if not code:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "confirmation_code_required"})
                return
            self._json(HTTPStatus.OK, {"status": "completed", "confirmation_code": code})
            return
        if parsed.path == "/v1/social/oauth/threads/start":
            ticket = str((urllib.parse.parse_qs(parsed.query).get("ticket") or [""])[0])
            if not ticket:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "social_browser_handoff_required"})
                return
            try:
                location, browser_session_id = self.runtime.begin_browser_connect(ticket)
            except (ValueError, PermissionError, RuntimeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            self._redirect(location, session_cookie=browser_session_id)
            return
        if parsed.path == "/v1/social/oauth/threads/callback":
            query = urllib.parse.parse_qs(parsed.query)
            state = str((query.get("state") or [""])[0])
            code = str((query.get("code") or [""])[0])
            browser_session_id = self._browser_session_cookie()
            if not state or not code or not browser_session_id:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "oauth_callback_context_required"})
                return
            try:
                location, _result = self.runtime.complete_connect(
                    state=state,
                    code=code,
                    browser_session_id=browser_session_id,
                )
            except (ValueError, PermissionError, RuntimeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}=; Path=/v1/social/oauth/threads/callback; Max-Age=0; HttpOnly; Secure; SameSite=Lax",
            )
            self.end_headers()
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/v1/social/webhooks/threads/deauthorize":
                self._json(HTTPStatus.OK, self.runtime.provider_deauthorize(self._signed_request()))
                return
            if parsed.path == "/v1/social/webhooks/threads/data-deletion":
                self._json(HTTPStatus.OK, self.runtime.provider_data_deletion(self._signed_request()))
                return

            body = self._body()
            request = self._request(body)
            if parsed.path == "/v1/social/status":
                self._product_auth(request)
                self._json(HTTPStatus.OK, self.runtime.status(request))
                return
            if parsed.path == "/v1/social/connect":
                self._product_auth(request)
                self._json(HTTPStatus.OK, self.runtime.connect(request))
                return
            if parsed.path in {"/v1/social/publish", "/v1/social/reply", "/v1/social/disconnect"}:
                self._product_auth(request)
                acceptance_id = self.headers.get("X-AgentOS-Acceptance-ID", "")
                self._json(HTTPStatus.OK, self.runtime.execute_write(request, acceptance_id))
                return
            if parsed.path == "/internal/v1/social/acceptances":
                value = self.runtime.issue_acceptance(request, self.headers.get("X-AgentOS-Control-Token", ""))
                self._json(HTTPStatus.CREATED, value)
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except PermissionError as exc:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": str(exc)})
        except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except RuntimeError as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def handler_for(runtime: SocialRuntime):
    class Handler(SocialRuntimeHandler):
        pass
    Handler.runtime = runtime
    return Handler


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, credential_path: str | Path = DEFAULT_CREDENTIAL_PATH) -> None:
    runtime = SocialRuntime.from_env(credential_path)
    ThreadingHTTPServer((host, port), handler_for(runtime)).serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--credential-path", default=str(DEFAULT_CREDENTIAL_PATH))
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.credential_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
