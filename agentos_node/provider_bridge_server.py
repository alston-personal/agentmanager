"""HTTP wake endpoint for the Agent Provider Bridge."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from typing import Any
from urllib.parse import urlparse

from .provider_bridge import AgentProviderBridge


MAX_REQUEST_BYTES = 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def validate_bridge_bind(host: str, token: str | None) -> None:
    if host not in LOOPBACK_HOSTS and not token:
        raise ValueError("AGENTOS_PROVIDER_BRIDGE_TOKEN is required for non-loopback binds")


class ProviderBridgeServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        bridge: AgentProviderBridge,
        *,
        token: str | None = None,
        max_workers: int = 4,
    ) -> None:
        host, _ = server_address
        validate_bridge_bind(host, token)
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.bridge = bridge
        self.auth_token = token
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agentos-provider")
        super().__init__(server_address, ProviderBridgeHandler)

    def submit_dispatch(self, envelope: dict[str, Any]) -> None:
        future = self.executor.submit(self.bridge.process_dispatch, envelope)

        def _report(done: Any) -> None:
            try:
                result = done.result()
                print(json.dumps({"provider_bridge": result}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            except Exception as exc:
                print(
                    json.dumps(
                        {"provider_bridge_error": type(exc).__name__, "message": str(exc)},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )

        future.add_done_callback(_report)

    def server_close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
        super().server_close()


class ProviderBridgeHandler(BaseHTTPRequestHandler):
    server: ProviderBridgeServer

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self) -> bool:
        expected = self.server.auth_token
        if not expected:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[7:], expected)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        length = int(raw_length)
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body too large")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON root must be an object")
        return value

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "agentos-provider-bridge",
                    "runtime_id": self.server.bridge.runtime_id,
                    "providers": self.server.bridge.registry.describe(),
                },
            )
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if urlparse(self.path).path != "/v1/runtime-dispatch":
            self._json(404, {"error": "not_found"})
            return
        try:
            envelope = self._body()
            dispatch_id = str(envelope.get("dispatch_id") or "")
            task_id = str(envelope.get("task_id") or "")
            if not dispatch_id or not task_id:
                raise ValueError("dispatch_id and task_id are required")
            self.server.submit_dispatch(envelope)
            self._json(
                202,
                {
                    "status": "accepted",
                    "external_ref": f"provider-bridge:{self.server.bridge.runtime_id}:{dispatch_id}",
                    "task_id": task_id,
                },
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return
