"""Minimal HTTP gateway for capability experience convergence.

It exposes only capability experience ingestion and canonical-state reads. The
browser never writes canonical state directly; reducers/evaluators/governance do
that through the AgentOS capability runtime/store.
"""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .capability_store import CapabilityStore

DEFAULT_ROOT = Path("/home/ubuntu/agent-data/runtime/capabilities")
MAX_BODY = 256 * 1024


class CapabilityGatewayHandler(BaseHTTPRequestHandler):
    store: CapabilityStore

    server_version = "AgentOSCapabilityGateway/0.1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request body size is invalid")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._json(HTTPStatus.OK, {"ok": True, "service": "agentos-capability-gateway", "version": "0.1"})
            return
        prefix = "/capability/"
        suffix = "/canonical"
        if self.path.startswith(prefix) and self.path.endswith(suffix):
            capability_id = unquote(self.path[len(prefix):-len(suffix)]).strip("/")
            try:
                state = self.store.read_state(capability_id, slot="canonical")
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if state is None:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "canonical state not found", "capability_id": capability_id})
            else:
                self._json(HTTPStatus.OK, {"ok": True, "state": state})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/capability/experience":
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        try:
            body = self._body()
            experiences = body.get("experiences")
            if experiences is None:
                experiences = [body.get("experience", body)]
            if not isinstance(experiences, list) or not experiences or len(experiences) > 20:
                raise ValueError("experiences must contain 1..20 items")
            if any(not isinstance(x, dict) for x in experiences):
                raise ValueError("each experience must be an object")
            receipts = self.store.ingest_many(experiences)
            self._json(HTTPStatus.ACCEPTED, {"ok": True, "receipts": receipts})
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        # The surrounding service manager owns access logging. Avoid leaking
        # capability payloads into generic web logs.
        return


def handler_for(store: CapabilityStore):
    class Handler(CapabilityGatewayHandler):
        pass
    Handler.store = store
    return Handler


def serve(host: str = "127.0.0.1", port: int = 8766, root: str | Path = DEFAULT_ROOT) -> None:
    store = CapabilityStore(root)
    store.ensure()
    server = ThreadingHTTPServer((host, port), handler_for(store))
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
