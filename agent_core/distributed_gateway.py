"""HTTP transport adapter for the Distributed AgentOS Control Plane.

The coordination semantics remain in DistributedControlPlane. This module only
translates authenticated JSON requests into submit/lease/complete operations.
It uses the Python standard library so the Core host does not gain a web-framework
dependency just to expose the MVP protocol.
"""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeResult

from .distributed_control_plane import DistributedControlPlane


MAX_REQUEST_BYTES = 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def validate_bind_security(host: str, token: str | None) -> None:
    if host not in LOOPBACK_HOSTS and not token:
        raise ValueError("AGENTOS_CONTROL_PLANE_TOKEN is required for non-loopback binds")


class DistributedGatewayService:
    """Transport-neutral request operations used by HTTP and future adapters."""

    def __init__(self, store: DistributedControlPlane) -> None:
        self.store = store

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        raw_ir = body.get("canonical_ir")
        if not isinstance(raw_ir, dict):
            raise ValueError("canonical_ir must be an object")
        ir = CanonicalIR.from_dict(raw_ir)
        task = self.store.submit_ir(
            ir,
            idempotency_key=body.get("idempotency_key"),
            target_node_id=body.get("target_node_id"),
        )
        return {"task": task, "inputDigest": ir.digest()}

    def lease(self, body: dict[str, Any]) -> dict[str, Any]:
        node_id = str(body.get("node_id") or "")
        capabilities = body.get("capabilities") or []
        if not node_id:
            raise ValueError("node_id is required")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise ValueError("capabilities must be an array of strings")
        lease_seconds = int(body.get("lease_seconds", 60))
        lease = self.store.lease_next_ir(node_id, capabilities, lease_seconds=lease_seconds)
        return {"lease": lease.to_dict() if lease else None}

    def lease_task(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        node_id = str(body.get("node_id") or "")
        if not node_id:
            raise ValueError("node_id is required")
        lease_seconds = int(body.get("lease_seconds", 60))
        lease = self.store.lease_ir_task(task_id, node_id, lease_seconds=lease_seconds)
        return {"lease": lease.to_dict() if lease else None}

    def complete(self, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        raw_result = body.get("runtime_result")
        if not isinstance(raw_result, dict):
            raise ValueError("runtime_result must be an object")
        enqueue = body.get("enqueue_continuation")
        if enqueue is not None and not isinstance(enqueue, bool):
            raise ValueError("enqueue_continuation must be boolean or omitted")
        return self.store.complete_ir(
            task_id,
            RemoteRuntimeResult.from_dict(raw_result),
            enqueue_continuation=enqueue,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return {"task": self.store.get_task(task_id)}


class DistributedGatewayServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: DistributedGatewayService,
        token: str | None = None,
    ) -> None:
        host, _ = server_address
        validate_bind_security(host, token)
        self.service = service
        self.auth_token = token
        super().__init__(server_address, DistributedGatewayHandler)


class DistributedGatewayHandler(BaseHTTPRequestHandler):
    server: DistributedGatewayServer

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = self.server.auth_token
        if not expected:
            return True
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        return hmac.compare_digest(header[len(prefix):], expected)

    def _read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        length = int(raw_length)
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("JSON root must be an object")
        return body

    def _route(self) -> tuple[str, list[str]]:
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        return path, parts

    def do_GET(self) -> None:
        path, parts = self._route()
        if path == "/health":
            self._json(200, {"status": "ok", "service": "distributed-agentos-control-plane"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        try:
            if len(parts) == 3 and parts[:2] == ["v1", "tasks"]:
                self._json(200, self.server.service.get_task(parts[2]))
                return
            self._json(404, {"error": "not_found"})
        except KeyError as exc:
            self._json(404, {"error": "not_found", "message": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        path, parts = self._route()
        try:
            body = self._read_body()
            if path == "/v1/ir/submit":
                self._json(200, self.server.service.submit(body))
                return
            if path == "/v1/lease":
                self._json(200, self.server.service.lease(body))
                return
            if len(parts) == 4 and parts[:2] == ["v1", "tasks"] and parts[3] == "lease":
                self._json(200, self.server.service.lease_task(parts[2], body))
                return
            if len(parts) == 4 and parts[:2] == ["v1", "tasks"] and parts[3] == "complete":
                self._json(200, self.server.service.complete(parts[2], body))
                return
            self._json(404, {"error": "not_found"})
        except KeyError as exc:
            self._json(404, {"error": "not_found", "message": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return
