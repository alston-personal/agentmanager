from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agent_core.controller_api import ControllerService
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer


def _online_fabric(tmp_path: Path) -> tuple[RealmFabricStore, str]:
    registry = NodeRegistry(tmp_path / 'nodes.json')
    fabric = RealmFabricStore(tmp_path / 'fabric.json', node_registry=registry)
    fabric.initialize_realm('realm-test')
    invite = fabric.create_invite()
    manifest = {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'role': 'client',
        'hostname': 'node-a',
        'platform': 'Windows',
        'platform_release': '11',
        'capabilities': ['agent.surface.inspect', 'desktop.open_url', 'shell.exec'],
        'tool_presence': {'python': 'C:/Python/python.exe'},
        'surface_inventory': {'surfaces': [], 'surface_count': 0, 'capabilities': []},
        'observed_at': '2099-01-01T00:00:00Z',
    }
    enrolled = fabric.enroll(invite_id=invite['invite_id'], code=invite['code'], manifest=manifest)
    token = enrolled['node_token']
    fabric.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'role': 'client',
        'status': 'online',
        'observed_at': '2099-01-01T00:00:00Z',
        'uptime_seconds': 1,
        'surface_count': 0,
        'manifest': manifest,
    }, token)
    return fabric, token


def test_controller_discovery_and_receipt_round_trip(tmp_path: Path) -> None:
    fabric, node_token = _online_fabric(tmp_path)
    controller = ControllerService(fabric)

    dispatched = controller.discover('node-a')
    assert dispatched['action'] == 'agent.surface.inspect'
    queued = fabric.pull_tasks('node-a', node_token)
    assert len(queued) == 1
    assert queued[0]['task_id'] == dispatched['task_id']
    assert queued[0]['action'] == 'agent.surface.inspect'

    fabric.record_receipt({
        'schema': 'agentos.node-receipt/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'task_id': dispatched['task_id'],
        'action': 'agent.surface.inspect',
        'ok': True,
        'surface_inventory': {'surface_count': 0, 'surfaces': []},
    }, node_token)
    receipt = controller.receipt(dispatched['task_id'])
    assert receipt['ok'] is True
    assert receipt['node_id'] == 'node-a'


def test_controller_rejects_arbitrary_shell_even_when_node_has_capability(tmp_path: Path) -> None:
    fabric, _ = _online_fabric(tmp_path)
    controller = ControllerService(fabric)
    with pytest.raises(PermissionError, match='controller action not permitted'):
        controller.dispatch('node-a', {'action': 'shell.exec', 'executable': 'cmd'})


def _request(url: str, token: str | None = None, *, method: str = 'GET', body: dict | None = None):
    headers = {'Accept': 'application/json'}
    if token is not None:
        headers['Authorization'] = f'Bearer {token}'
    data = None if body is None else json.dumps(body).encode('utf-8')
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read().decode('utf-8'))


def test_http_controller_requires_separate_credential_and_dispatches(tmp_path: Path) -> None:
    fabric, node_token = _online_fabric(tmp_path)
    server = RealmHTTPServer(('127.0.0.1', 0), fabric, controller_token='controller-secret')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        with pytest.raises(urllib.error.HTTPError) as missing:
            _request(base + '/v1/controller/nodes')
        assert missing.value.code == 401

        with pytest.raises(urllib.error.HTTPError) as node_credential:
            _request(base + '/v1/controller/nodes', node_token)
        assert node_credential.value.code == 401

        status, nodes = _request(base + '/v1/controller/nodes', 'controller-secret')
        assert status == 200
        assert nodes['node_map']['online_node_count'] == 1

        status, dispatched = _request(
            base + '/v1/controller/nodes/node-a/discover',
            'controller-secret',
            method='POST',
            body={},
        )
        assert status == 202
        assert dispatched['action'] == 'agent.surface.inspect'
        queued = fabric.pull_tasks('node-a', node_token)
        assert queued[0]['task_id'] == dispatched['task_id']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
