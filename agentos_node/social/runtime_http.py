from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
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
from .runtime_storage import FileCredentialVault, OneShotAcceptanceStore
from .threads import ThreadsCapability, ThreadsProviderConfig, ThreadsProviderTransport

MAX_BODY = 64 * 1024
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
DEFAULT_CREDENTIAL_PATH = Path("/home/ubuntu/agent-data/runtime/social/credentials.json")
SESSION_COOKIE = "agentos_social_session"


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


class BrowserContextStore:
    """Short-lived in-process callback context. Restart fails closed."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def bind(self, state: str, product_id: str, browser_session_id: str) -> None:
        with self._lock:
            self._items[state] = (product_id, browser_session_id)

    def consume(self, state: str, browser_session_id: str) -> tuple[str, str]:
        with self._lock:
            value = self._items.pop(state, None)
        if value is None:
            raise PermissionError("social_oauth_browser_context_invalid_or_consumed")
        product_id, expected_session = value
        if not hmac.compare_digest(expected_session, str(browser_session_id or "")):
            raise PermissionError("social_oauth_browser_session_mismatch")
        return product_id, expected_session


class SocialRuntime:
    def __init__(
        self,
        *,
        products: ProductRegistry,
        threads: ThreadsCapability,
        acceptances: OneShotAcceptanceStore | None = None,
        browser_contexts: BrowserContextStore | None = None,
        control_token: str = "",
    ) -> None:
        self.products = products
        self.threads = threads
        self.acceptances = acceptances or OneShotAcceptanceStore()
        self.browser_contexts = browser_contexts or BrowserContextStore()
        self.control_token = control_token

    @classmethod
    def from_env(cls, credential_path: str | Path = DEFAULT_CREDENTIAL_PATH) -> "SocialRuntime":
        products = ProductRegistry.from_env()
        vault = FileCredentialVault(credential_path)

        def config_loader() -> ThreadsProviderConfig:
            return ThreadsProviderConfig(
                app_id=os.environ.get("AGENTOS_THREADS_APP_ID", ""),
                app_secret=os.environ.get("AGENTOS_THREADS_APP_SECRET", ""),
                redirect_uri=os.environ.get("AGENTOS_THREADS_REDIRECT_URI", ""),
            )

        return cls(
            products=products,
            threads=ThreadsCapability(vault, ThreadsProviderTransport(config_loader)),
            control_token=os.environ.get("AGENTOS_SOCIAL_CONTROL_TOKEN", ""),
        )

    def configured_status(self) -> dict[str, Any]:
        return {
            "schema": "agentos.social-runtime-status/v1",
            "service": "agentos-social-runtime",
            "threads": {"configured": self.threads._configured()},
        }

    def status(self, request: SocialRequest) -> dict[str, Any]:
        self.products.registration(request.product_id)
        return self.threads.status(request)

    def connect(self, request: SocialRequest) -> dict[str, Any]:
        self.products.registration(request.product_id)
        browser_session_id = secrets.token_urlsafe(24)
        value = self.threads.begin_connect(request, browser_session_id=browser_session_id)
        state = value.pop("state")
        self.browser_contexts.bind(state, request.product_id, browser_session_id)
        return {**value, "browser_session_id": browser_session_id}

    def complete_connect(self, *, state: str, code: str, browser_session_id: str) -> tuple[str, dict[str, Any]]:
        product_id, expected_session = self.browser_contexts.consume(state, browser_session_id)
        registration = self.products.registration(product_id)
        result = self.threads.complete_connect(
            product_id=product_id,
            browser_session_id=expected_session,
            state=state,
            code=code,
        )
        relative = sanitized_oauth_return(
            str(result.get("return_to") or "/"),
            connected=True,
            binding_id=str(result.get("binding_id") or ""),
        )
        return registration.return_base + relative, {
            "schema": "agentos.social-oauth-complete/v1",
            "connected": True,
            "binding_id": result.get("binding_id"),
            "account": result.get("account"),
        }

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

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request_body_size_invalid")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("json_object_required")
        return value

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
            body = self._body()
            request = self._request(body)
            if self.path == "/v1/social/status":
                self._product_auth(request)
                self._json(HTTPStatus.OK, self.runtime.status(request))
                return
            if self.path == "/v1/social/connect":
                self._product_auth(request)
                value = self.runtime.connect(request)
                browser_session_id = str(value.pop("browser_session_id"))
                self._json(HTTPStatus.OK, value, session_cookie=browser_session_id)
                return
            if self.path in {"/v1/social/publish", "/v1/social/reply", "/v1/social/disconnect"}:
                self._product_auth(request)
                acceptance_id = self.headers.get("X-AgentOS-Acceptance-ID", "")
                self._json(HTTPStatus.OK, self.runtime.execute_write(request, acceptance_id))
                return
            if self.path == "/internal/v1/social/acceptances":
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
        # Avoid writing OAuth codes, write payloads, or product content to generic logs.
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
