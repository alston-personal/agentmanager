from __future__ import annotations

import json
from pathlib import Path

from agent_core.controller_api import ControllerService
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.runtime_ota import RuntimeOTAPolicyStore
from agentos_node.runtime_provenance import SCHEMA, observe_runtime


def _manifest(node_id: str, runtime_commit: str | None = None) -> dict:
    runtime = {'schema': SCHEMA, 'status': 'unknown'}
    if runtime_commit:
        runtime.update({'status': 'observed', 'source_ref': 'feature/realm-node-fabric-readiness', 'source_commit': runtime_commit})
    return {
        'schema': 'agentos.node-manifest/v0.1',
        'realm_id': 'realm-test',
        'node_id': node_id,
        'role': 'client',
        'hostname': node_id,
        'platform': 'Windows',
        'platform_release': '11',
        'capabilities': ['agent.surface.inspect', 'shell.exec'],
        'tool_presence': {'powershell': 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'},
        'surface_inventory': {'surfaces': [], 'surface_count': 0, 'capabilities': []},
        'runtime': runtime,
        'observed_at': '2099-01-01T00:00:00Z',
    }


def _enroll_online(fabric: RealmFabricStore, node_id: str, runtime_commit: str | None = None) -> str:
    invite = fabric.create_invite()
    manifest = _manifest(node_id, runtime_commit)
    enrolled = fabric.enroll(invite_id=invite['invite_id'], code=invite['code'], manifest=manifest)
    token = enrolled['node_token']
    fabric.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': node_id,
        'role': 'client',
        'status': 'online',
        'observed_at': '2099-01-01T00:00:00Z',
        'uptime_seconds': 1,
        'surface_count': 0,
        'manifest': manifest,
    }, token)
    return token


def test_runtime_provenance_reads_installed_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / 'runtime-provenance.json'
    path.write_text(json.dumps({
        'schema': SCHEMA,
        'source_ref': 'main',
        'source_commit': 'a' * 40,
        'installed_at': '2026-08-28T00:00:00Z',
    }), encoding='utf-8')
    monkeypatch.setenv('AGENTOS_RUNTIME_PROVENANCE', str(path))
    observed = observe_runtime()
    assert observed['status'] == 'observed'
    assert observed['source_commit'] == 'a' * 40
    assert observed['provenance_path'] == str(path)


def test_realm_rollout_queues_only_nonconverged_and_requires_post_restart_heartbeat(tmp_path: Path) -> None:
    desired = 'b' * 40
    ota = RuntimeOTAPolicyStore(tmp_path / 'runtime-ota.json')
    registry = NodeRegistry(tmp_path / 'nodes.json', ota_policy=ota)
    fabric = RealmFabricStore(tmp_path / 'fabric.json', node_registry=registry)
    fabric.initialize_realm('realm-test')
    token_a = _enroll_online(fabric, 'node-a')
    token_b = _enroll_online(fabric, 'node-b', desired)
    controller = ControllerService(fabric, ota_policy=ota)

    rollout = controller.rollout_runtime({
        'source_ref': 'feature/realm-node-fabric-readiness',
        'source_commit': desired,
        'task_id': 'ota_test',
    })
    assert rollout['queued_node_count'] == 1
    assert rollout['nodes'][0]['node_id'] == 'node-a'
    assert {'node_id': 'node-b', 'reason': 'already_converged'} in rollout['skipped']

    tasks_a = fabric.pull_tasks('node-a', token_a)
    assert len(tasks_a) == 1
    task = tasks_a[0]
    assert task['controller_action'] == 'node.runtime.converge'
    script = task['argv'][-1]
    assert 'agentos_node/runtime_provenance.py' in script
    assert 'runtime-provenance.json' in script
    assert 'Register-ScheduledTask' not in script
    assert fabric.pull_tasks('node-b', token_b) == []

    fabric.record_receipt({
        'schema': 'agentos.node-receipt/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'task_id': task['task_id'],
        'action': 'shell.exec',
        'ok': True,
    }, token_a)
    before_restart_heartbeat = controller.verify_runtime_rollout('ota_test')
    assert before_restart_heartbeat['ok'] is False
    assert before_restart_heartbeat['pending_node_count'] == 1

    manifest = _manifest('node-a', desired)
    fabric.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'role': 'client',
        'status': 'online',
        'observed_at': '2099-01-01T00:00:01Z',
        'uptime_seconds': 1,
        'surface_count': 0,
        'manifest': manifest,
    }, token_a)
    verified = controller.verify_runtime_rollout('ota_test')
    assert verified['ok'] is True
    assert verified['converged_node_count'] == 2
    assert verified['pending_node_count'] == 0

    node_map = controller.nodes()
    assert node_map['runtime_converged_count'] == 2
    assert all(node['runtime_status'] == 'converged' for node in node_map['nodes'])
