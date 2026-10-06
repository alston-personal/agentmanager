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


def _online_fabric(tmp_path: Path, *, include_workspace_roots: bool = True, platform_name: str = 'Windows') -> tuple[RealmFabricStore, str]:
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
        'platform': platform_name,
        'platform_release': '11' if platform_name == 'Windows' else '6.8.0',
        'capabilities': [
            'agent.surface.inspect', 'desktop.open_url', 'shell.exec',
            'desktop.windows.tile', 'desktop.mouse', 'desktop.keyboard',
        ],
        'tool_presence': {'python': 'C:/Python/python.exe'} if platform_name == 'Windows' else {'python3': '/usr/bin/python3', 'git': '/usr/bin/git'},
        'surface_inventory': {'surfaces': [], 'surface_count': 0, 'capabilities': []},
        'observed_at': '2099-01-01T00:00:00Z',
    }
    if include_workspace_roots:
        manifest['workspace_roots'] = {
            'readable': ['C:/Users/test/AgentOS'] if platform_name == 'Windows' else ['/home/test'],
            'writable': ['C:/Users/test/AgentOS'] if platform_name == 'Windows' else ['/home/test'],
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


def test_typed_desktop_actions_map_to_bounded_node_capabilities(tmp_path: Path) -> None:
    fabric, node_token = _online_fabric(tmp_path)
    controller = ControllerService(fabric)

    staged = controller.dispatch('node-a', {
        'action': 'desktop.window.stage',
        'title_contains': 'Google Gemini',
        'zone': 'full',
        'reserve_top_px': 8,
        'margin_px': 4,
        'unexpected': 'must-not-pass-through',
    })
    assert staged['action'] == 'desktop.window.stage'
    task = fabric.pull_tasks('node-a', node_token)[0]
    assert task == {
        'schema': 'agentos.node-task/v0.1',
        'task_id': staged['task_id'],
        'controller_action': 'desktop.window.stage',
        'cognition_ids_used': [],
        'action': 'desktop.windows.tile',
        'windows': [{'title_contains': 'Google Gemini', 'zone': 'full'}],
        'reserve_top_px': 8,
        'margin_px': 4,
    }

    clicked = controller.dispatch('node-a', {
        'action': 'desktop.pointer.click', 'x': 123, 'y': 456, 'button': 'left',
    })
    task = fabric.pull_tasks('node-a', node_token)[0]
    assert task['task_id'] == clicked['task_id']
    assert task['action'] == 'desktop.mouse'
    assert task['controller_action'] == 'desktop.pointer.click'
    assert task['operation'] == 'click'
    assert (task['x'], task['y'], task['button']) == (123, 456, 'left')

    typed = controller.dispatch('node-a', {
        'action': 'desktop.text.insert', 'text': 'hello Gemini',
    })
    task = fabric.pull_tasks('node-a', node_token)[0]
    assert task['task_id'] == typed['task_id']
    assert task['action'] == 'desktop.keyboard'
    assert task['controller_action'] == 'desktop.text.insert'
    assert task['operation'] == 'type'
    assert task['text'] == 'hello Gemini'


@pytest.mark.parametrize('request', [
    {'action': 'desktop.window.stage', 'title_contains': 'x', 'zone': 'diagonal'},
    {'action': 'desktop.window.stage', 'title_contains': '', 'zone': 'full'},
    {'action': 'desktop.pointer.click', 'x': -1, 'y': 5},
    {'action': 'desktop.pointer.click', 'x': 5, 'y': 5, 'button': 'middle'},
    {'action': 'desktop.text.insert', 'text': ''},
    {'action': 'desktop.text.insert', 'text': 'x' * 1001},
])
def test_typed_desktop_actions_reject_out_of_contract_payloads(tmp_path: Path, request: dict) -> None:
    fabric, _ = _online_fabric(tmp_path)
    controller = ControllerService(fabric)
    with pytest.raises(ValueError):
        controller.dispatch('node-a', request)


def test_runtime_convergence_constructs_fixed_shell_and_preserves_watchdog(tmp_path: Path) -> None:
    fabric, node_token = _online_fabric(tmp_path)
    controller = ControllerService(fabric)
    commit = 'a' * 40
    result = controller.dispatch('node-a', {
        'action': 'node.runtime.converge',
        'source_commit': commit,
        'executable': 'cmd.exe',
        'argv': ['/c', 'whoami'],
    })
    assert result['action'] == 'node.runtime.converge'
    queued = fabric.pull_tasks('node-a', node_token)
    assert len(queued) == 1
    task = queued[0]
    assert task['action'] == 'shell.exec'
    assert task['controller_action'] == 'node.runtime.converge'
    assert task['executable'] == 'powershell'
    assert task['cwd'] == 'C:/Users/test/AgentOS'
    script = task['argv'][-1]
    assert commit in script
    assert 'AgentOS Thin Client Watchdog' in script
    assert 'Register-ScheduledTask' not in script
    assert 'whoami' not in script
    assert 'cmd.exe' not in script
    assert "Start-Sleep -Seconds 10" in script
    assert "Get-CimInstance Win32_Process" in script
    assert "agentos_node\\.client_cli\\s+run" in script
    assert "Stop-Process -Id $proc.ProcessId" in script
    assert "Start-ScheduledTask -TaskName $taskName" in script
    assert "managed_client_count=$clients.Count" in script
    assert "thin_client_task_state=$state" in script
    assert "runtime-convergence.json" in script
    assert "controller-single-owner-converge" in script
    assert "agentos_single_owner_convergence=DEFERRED" in script

    with pytest.raises(ValueError, match='source_commit'):
        controller.dispatch('node-a', {'action': 'node.runtime.converge', 'source_commit': 'main'})


def test_linux_runtime_convergence_uses_python_and_deferred_systemd_restart(tmp_path: Path) -> None:
    fabric, node_token = _online_fabric(tmp_path, platform_name='Linux')
    controller = ControllerService(fabric)
    commit = 'b' * 40
    result = controller.dispatch('node-a', {
        'action': 'node.runtime.converge',
        'source_commit': commit,
        'source_ref': 'core/integration',
    })
    assert result['action'] == 'node.runtime.converge'
    queued = fabric.pull_tasks('node-a', node_token)
    assert len(queued) == 1
    task = queued[0]
    assert task['action'] == 'shell.exec'
    assert task['controller_action'] == 'node.runtime.converge'
    assert task['executable'] == 'python3'
    assert task['cwd'] == '/home/test'
    script = task['argv'][-1]
    assert commit in script
    assert "git','-C',str(repo),'fetch'" in script
    assert "git','-C',str(repo),'checkout','--detach'" in script
    assert 'runtime-provenance.json' in script
    assert 'agentos-thin-client.service' in script
    assert 'start_new_session=True' in script
    assert 'agentos_single_owner_convergence=DEFERRED' in script


def test_runtime_convergence_requires_node_workspace_authority(tmp_path: Path) -> None:
    fabric, _ = _online_fabric(tmp_path, include_workspace_roots=False)
    controller = ControllerService(fabric)
    with pytest.raises(ValueError, match='workspace roots'):
        controller.dispatch('node-a', {
            'action': 'node.runtime.converge',
            'source_commit': 'a' * 40,
        })


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


def test_controller_scheduler_projection_is_bounded_and_http_readable(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / 'agent-data'
    runtime = data_root / 'runtime' / 'bootstrap-scheduler'
    incidents = runtime / 'incidents'
    incidents.mkdir(parents=True)
    (runtime / 'status.json').write_text(json.dumps({
        'schema': 'agentos.bootstrap-scheduler-status/v1',
        'node': 'oracle',
        'updated_at': '2026-09-30T05:30:00Z',
        'queue_depth': {'control': 1, 'social': 2, 'gui': 1, 'build': 0},
        'workers': {
            'oracle-gui': {
                'role': 'gui',
                'state': 'running',
                'heartbeat': '2026-09-30T05:30:00Z',
                'current_job': {
                    'request_id': 'mio-dm-test',
                    'action': 'agentos.social_threads_web_dm.read',
                    'priority': 'high',
                    'locks': ['threads-mio-gui'],
                    'private_path': '/home/ubuntu/private',
                },
            },
            'agentos-router': {
                'role': 'router',
                'state': 'idle',
                'heartbeat': '2026-09-30T05:30:00Z',
                'current_job': None,
            },
        },
    }), encoding='utf-8')
    (incidents / 'incident.json').write_text(json.dumps({
        'schema': 'agentos.scheduler-incident/v1',
        'project': 'mio',
        'request_id': 'mio-dm-test',
        'action': 'agentos.social_threads_web_dm.read',
        'priority': 'high',
        'requested_capabilities': ['threads.gui.read'],
        'preferred_node': 'oracle',
        'failure_class': 'queue_starvation',
        'fallback_attempted': True,
        'receipt_required': True,
        'observed_at': '2026-09-30T05:30:00Z',
        'detail': 'Bearer secret-must-not-project',
    }), encoding='utf-8')
    monkeypatch.setenv('AGENT_DATA_ROOT', str(data_root))

    fabric, _ = _online_fabric(tmp_path / 'realm')
    controller = ControllerService(fabric)
    pool = controller.scheduler()
    assert pool['schema'] == 'agentos.runner-pool/v1'
    assert pool['worker_count'] == 2
    assert pool['busy_worker_count'] == 1
    assert pool['queue_depth']['gui'] == 1
    assert pool['lock_holders']['threads-mio-gui'] == 'oracle-gui'
    assert pool['workers']['oracle-gui']['current_job']['action'] == 'agentos.social_threads_web_dm.read'
    assert 'private_path' not in pool['workers']['oracle-gui']['current_job']
    assert pool['recent_incidents'][0]['failure_class'] == 'queue_starvation'
    assert 'detail' not in pool['recent_incidents'][0]

    server = RealmHTTPServer(('127.0.0.1', 0), fabric, controller_token='controller-secret')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        with pytest.raises(urllib.error.HTTPError) as missing:
            _request(base + '/v1/controller/scheduler')
        assert missing.value.code == 401

        status, payload = _request(base + '/v1/controller/scheduler', 'controller-secret')
        assert status == 200
        assert payload['runner_pool']['schema'] == 'agentos.runner-pool/v1'
        assert payload['runner_pool']['workers']['agentos-router']['role'] == 'router'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
