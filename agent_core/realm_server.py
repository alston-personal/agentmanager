from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import socket
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent_core.controller_api import ControllerService as RuntimeControllerService
from agent_core.controller_service import ControllerService as LegacyControllerService
from agent_core.node_bootstrap import bootstrap_snapshot, record_join_regression
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.resolve_facade import resolve_continuation


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _core_node_manifest(realm_id: str) -> dict[str, Any]:
    node_id = str(os.environ.get('AGENTOS_CORE_NODE_ID') or 'oracle-core-node').strip()
    if not node_id:
        raise ValueError('AGENTOS_CORE_NODE_ID cannot be empty')
    tools = {name: bool(shutil.which(name)) for name in ('git', 'python3', 'curl', 'systemctl')}
    return {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': realm_id,
        'node_id': node_id,
        'role': 'core',
        'hostname': socket.gethostname(),
        'platform': platform.system(),
        'platform_release': platform.release(),
        'capabilities': ['agentos.governance.read', 'agentos.one.resolve', 'agentos.realm.fabric'],
        'tool_presence': tools,
        'surface_inventory': {'surfaces': []},
        'observed_at': _utc_now(),
    }


def _core_node_heartbeat(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': manifest['realm_id'],
        'node_id': manifest['node_id'],
        'status': 'online',
        'observed_at': _utc_now(),
        'uptime_seconds': None,
        'surface_count': len((manifest.get('surface_inventory') or {}).get('surfaces') or []),
        'manifest': {**manifest, 'observed_at': _utc_now()},
    }


def _run_core_node_heartbeat(registry: NodeRegistry, manifest: dict[str, Any], stop: threading.Event) -> None:
    interval = max(5, int(os.environ.get('AGENTOS_CORE_HEARTBEAT_SECONDS', '10')))
    while not stop.is_set():
        try:
            registry.record_heartbeat(_core_node_heartbeat(manifest))
        except Exception:
            pass
        stop.wait(interval)


class RealmRequestHandler(BaseHTTPRequestHandler):
    server_version = 'AgentOS-ONE/0.1'

    @property
    def fabric(self) -> RealmFabricStore:
        return self.server.fabric  # type: ignore[attr-defined]

    @property
    def controller(self) -> RuntimeControllerService:
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
                result = self.fabric.request_join(manifest=dict(body.get('manifest') or {}), expires_minutes=int(body.get('expires_minutes') or 10))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/status':
                body = self._json_body()
                result = self.fabric.join_status(request_id=str(body.get('request_id') or ''), claim_secret=str(body.get('claim_secret') or ''))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/join/claim':
                body = self._json_body()
                result = self.fabric.claim_join(request_id=str(body.get('request_id') or ''), claim_secret=str(body.get('claim_secret') or ''))
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/enroll':
                body = self._json_body()
                result = self.fabric.enroll(invite_id=str(body.get('invite_id') or ''), code=str(body.get('code') or ''), manifest=dict(body.get('manifest') or {}))
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
                    and (effective.get('workspace_roots') or {}).get('readable')
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
            # Compatibility fence: preserve the live-accepted #64 transport contract.
            # Privileged runtime/controller surfaces below remain separately authenticated.
            if parsed.path == '/v1/controller/dispatch':
                body = self._json_body()
                result = LegacyControllerService(self.fabric).dispatch(body)
                self._send(200, result)
                return
            if parsed.path == '/v1/resolve':
                body = self._json_body()
                if body.get('schema') not in (None, 'agentos.resolve-request/v1'):
                    raise ValueError('invalid resolve request schema')
                if str(body.get('intent') or 'continue') != 'continue':
                    raise ValueError('only continue intent is supported in v1')
                node_id = str(body.get('node_id') or '')
                if not node_id:
                    raise ValueError('node_id is required')
                token = self._bearer()
                self.fabric.authenticate(node_id, token)
                node_context = bootstrap_snapshot(self.fabric, node_id, token)
                project_query = str(body.get('project') or body.get('query') or '').strip()
                if not project_query:
                    raise ValueError('project query is required')
                result = resolve_continuation(project_query, node_context=node_context)
                self._send(200, {'ok': True, **result})
                return
            if parsed.path == '/v1/controller/runtime/rollout':
                self._authorize_controller()
                result = self.controller.rollout_runtime(self._json_body())
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
        self.controller = RuntimeControllerService(fabric)
        self.controller_token = controller_token if controller_token is not None else os.environ.get('AGENTOS_CONTROLLER_TOKEN', '')


def serve(*, host: str = '127.0.0.1', port: int = 8780, fabric: RealmFabricStore | None = None, controller_token: str | None = None) -> None:
    store = fabric or RealmFabricStore()
    realm = store.load()
    realm_id = str(realm.get('realm_id') or '').strip()
    if not realm_id:
        raise ValueError('initialize Realm before serving')

    registry = store.node_registry
    manifest = _core_node_manifest(realm_id)
    registry.register_manifest(manifest)
    registry.record_heartbeat(_core_node_heartbeat(manifest))
    stop = threading.Event()
    heartbeat = threading.Thread(target=_run_core_node_heartbeat, args=(registry, manifest, stop), name='agentos-core-node-heartbeat', daemon=True)
    heartbeat.start()

    server = RealmHTTPServer((host, port), store, controller_token=controller_token)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        heartbeat.join(timeout=2)
        server.server_close()
