from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent_core.realm_fabric import RealmFabricStore


class RealmRequestHandler(BaseHTTPRequestHandler):
    server_version = 'AgentOS-ONE/0.1'

    @property
    def fabric(self) -> RealmFabricStore:
        return self.server.fabric  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        return super().log_message(fmt, *args)

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception as exc:
            raise ValueError(f'invalid JSON body: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('JSON body must be an object')
        return payload

    def _bearer(self) -> str:
        value = self.headers.get('Authorization') or ''
        prefix = 'Bearer '
        if not value.startswith(prefix):
            raise PermissionError('missing bearer credential')
        return value[len(prefix):].strip()

    def _send(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            code = HTTPStatus.UNAUTHORIZED
        elif isinstance(exc, KeyError):
            code = HTTPStatus.NOT_FOUND
        elif isinstance(exc, ValueError):
            code = HTTPStatus.BAD_REQUEST
        else:
            code = HTTPStatus.INTERNAL_SERVER_ERROR
        self._send(int(code), {'ok': False, 'error': f'{type(exc).__name__}: {exc}'})

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/v1/health':
                data = self.fabric.load()
                self._send(200, {'ok': True, 'schema': 'agentos.one-health/v0.1', 'realm_id': data.get('realm_id')})
                return
            if parsed.path == '/v1/tasks':
                query = parse_qs(parsed.query)
                node_id = (query.get('node_id') or [''])[0]
                token = self._bearer()
                tasks = self.fabric.pull_tasks(node_id, token)
                self._send(200, {'ok': True, 'tasks': tasks})
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == '/v1/join/request':
                body = self._json_body()
                result = self.fabric.request_join(
                    manifest=dict(body.get('manifest') or {}),
                    expires_minutes=int(body.get('expires_minutes') or 10),
                )
                self._send(200, {'ok': True, **result})
                return
            if self.path == '/v1/join/status':
                body = self._json_body()
                result = self.fabric.join_status(
                    request_id=str(body.get('request_id') or ''),
                    claim_secret=str(body.get('claim_secret') or ''),
                )
                self._send(200, {'ok': True, **result})
                return
            if self.path == '/v1/join/claim':
                body = self._json_body()
                result = self.fabric.claim_join(
                    request_id=str(body.get('request_id') or ''),
                    claim_secret=str(body.get('claim_secret') or ''),
                )
                self._send(200, {'ok': True, **result})
                return
            if self.path == '/v1/enroll':
                body = self._json_body()
                result = self.fabric.enroll(
                    invite_id=str(body.get('invite_id') or ''),
                    code=str(body.get('code') or ''),
                    manifest=dict(body.get('manifest') or {}),
                )
                self._send(200, {'ok': True, **result})
                return
            if self.path == '/v1/heartbeat':
                body = self._json_body()
                token = self._bearer()
                node = self.fabric.record_heartbeat(body, token)
                self._send(200, {'ok': True, 'node': node})
                return
            if self.path == '/v1/receipts':
                body = self._json_body()
                token = self._bearer()
                receipt = self.fabric.record_receipt(body, token)
                self._send(200, {'ok': True, 'receipt': receipt})
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)


class RealmHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], fabric: RealmFabricStore):
        super().__init__(address, RealmRequestHandler)
        self.fabric = fabric


def serve(*, host: str = '127.0.0.1', port: int = 8780, fabric: RealmFabricStore | None = None) -> None:
    server = RealmHTTPServer((host, port), fabric or RealmFabricStore())
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
