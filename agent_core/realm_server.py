from __future__ import annotations

import json
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent_core.controller_api import ControllerService
from agent_core.node_bootstrap import bootstrap_snapshot, record_join_regression
from agent_core.realm_fabric import RealmFabricStore


class RealmRequestHandler(BaseHTTPRequestHandler):
    server_version = 'AgentOS-ONE/0.1'

    @property
    def fabric(self) -> RealmFabricStore:
        return self.server.fabric  # type: ignore[attr-defined]

    @property
    def controller(self) -> ControllerService:
        return self.server.controller  # type: ignore[attr-defined]

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

    def _authorize_controller(self) -> None:
        expected = str(getattr(self.server, 'controller_token', '') or '')  # type: ignore[attr-defined]
        if not expected:
            raise PermissionError('controller API disabled')
        supplied = self._bearer()
        if not secrets.compare_digest(supplied, expected):
            raise PermissionError('invalid controller credential')

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
            if parsed.path == '/v1/bootstrap':
                query = parse_qs(parsed.query)
                node_id = (query.get('node_id') or [''])[0]
                token = self._bearer()
                snapshot = bootstrap_snapshot(self.fabric, node_id, token)
                self._send(200, {'ok': True, **snapshot})
                return
            if parsed.path == '/v1/controller/realm':
                self._authorize_controller()
                self._send(200, {'ok': True, 'realm': self.controller.realm()})
                return
            if parsed.path == '/v1/controller/nodes':
                self._authorize_controller()
                self._send(200, {'ok': True, 'node_map': self.controller.nodes()})
                return
            rollout_prefix = '/v1/controller/runtime/rollouts/'
            if parsed.path.startswith(rollout_prefix):
                self._authorize_controller()
                rollout_id = parsed.path.removeprefix(rollout_prefix).strip('/')
                if not rollout_id or '/' in rollout_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'rollout': self.controller.verify_runtime_rollout(rollout_id)})
                return
            if parsed.path.startswith('/v1/controller/nodes/'):
                self._authorize_controller()
                node_id = parsed.path.removeprefix('/v1/controller/nodes/').strip('/')
                if not node_id or '/' in node_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'node': self.controller.node(node_id)})
                return
            if parsed.path.startswith('/v1/controller/receipts/'):
                self._authorize_controller()
                task_id = parsed.path.removeprefix('/v1/controller/receipts/').strip('/')
                if not task_id or '/' in task_id:
                    raise KeyError(parsed.path)
                self._send(200, {'ok': True, 'receipt': self.controller.receipt(task_id)})
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == '/v1/join/request':
                body = self._json_body()
                result = self.fabric.request_join(
                    manifest=dict(body.get('manifest') or {}),
                    expires_minutes=int(body.get('expires_minutes') or 10),
                )
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/status':
                body = self._json_body()
                result = self.fabric.join_status(
                    request_id=str(body.get('request_id') or ''),
                    claim_secret=str(body.get('claim_secret') or ''),
                )
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/claim':
                body = self._json_body()
                result = self.fabric.claim_join(
                    request_id=str(body.get('request_id') or ''),
                    claim_secret=str(body.get('claim_secret') or ''),
                )
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/enroll':
                body = self._json_body()
                result = self.fabric.enroll(
                    invite_id=str(body.get('invite_id') or ''),
                    code=str(body.get('code') or ''),
                    manifest=dict(body.get('manifest') or {}),
                )
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/heartbeat':
                body = self._json_body()
                token = self._bearer()
                node = self.fabric.record_heartbeat(body, token)
                auto_ota = None
                policy = self.controller.ota_policy.load()
                desired = str(policy.get('desired_source_commit') or '')
                node_id = str(body.get('node_id') or '')
                effective = self.controller.node(node_id)
                if (
                    policy.get('auto_converge') is True
                    and desired
                    and effective.get('status') == 'online'
                    and effective.get('runtime_status') != 'converged'
                    and 'shell.exec' in set(effective.get('capabilities') or [])
                ):
                    auto_ota = self.controller.dispatch(node_id, {
                        'action': 'node.runtime.converge',
                        'task_id': f'auto_ota_{desired[:12]}_{node_id}',
                        'source_ref': str(policy.get('desired_source_ref') or 'feature/realm-node-fabric-readiness'),
                        'source_commit': desired,
                    })
                self._send(200, {'ok': True, 'node': node, 'auto_ota': auto_ota})
                return
            if parsed.path == '/v1/benchmark':
                body = self._json_body()
                token = self._bearer()
                node_id = str(body.get('node_id') or '')
                report = record_join_regression(self.fabric, node_id, token, body)
                self._send(200, {'ok': True, 'benchmark': report})
                return
            if parsed.path == '/v1/receipts':
                body = self._json_body()
                token = self._bearer()
                receipt = self.fabric.record_receipt(body, token)
                self._send(200, {'ok': True, 'receipt': receipt})
                return
            if parsed.path == '/v1/controller/runtime/rollout':
                self._authorize_controller()
                result = self.controller.rollout_runtime(self._json_body())
                self._send(202, result)
                return
            if parsed.path == '/v1/controller/dispatch':
                self._authorize_controller()
                body = self._json_body()
                node_id = str(body.pop('node_id', '') or '')
                result = self.controller.dispatch(node_id, body)
                self._send(202, result)
                return
            prefix = '/v1/controller/nodes/'
            suffix = '/discover'
            if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
                self._authorize_controller()
                node_id = parsed.path[len(prefix):-len(suffix)].strip('/')
                if not node_id or '/' in node_id:
                    raise KeyError(parsed.path)
                result = self.controller.discover(node_id)
                self._send(202, result)
                return
            self._send(404, {'ok': False, 'error': 'not found'})
        except Exception as exc:
            self._error(exc)


class RealmHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], fabric: RealmFabricStore, *, controller_token: str | None = None):
        super().__init__(address, RealmRequestHandler)
        self.fabric = fabric
        self.controller = ControllerService(fabric)
        self.controller_token = controller_token if controller_token is not None else os.environ.get('AGENTOS_CONTROLLER_TOKEN', '')


def serve(*, host: str = '127.0.0.1', port: int = 8780, fabric: RealmFabricStore | None = None, controller_token: str | None = None) -> None:
    server = RealmHTTPServer((host, port), fabric or RealmFabricStore(), controller_token=controller_token)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
