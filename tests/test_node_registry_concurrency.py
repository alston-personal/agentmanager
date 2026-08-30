from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

from agent_core.node_registry import NodeRegistry


def _heartbeat_worker(path: str, node_id: str, loops: int) -> None:
    registry = NodeRegistry(Path(path))
    for i in range(loops):
        registry.record_heartbeat({
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': 'realm-test',
            'node_id': node_id,
            'status': 'online',
            'observed_at': f'2026-08-29T08:00:{i % 60:02d}Z',
            'uptime_seconds': i,
            'surface_count': 1,
            'manifest': {
                'schema': 'agentos.node-manifest/v0.1',
                'realm_id': 'realm-test',
                'node_id': node_id,
                'role': 'client',
                'hostname': node_id,
                'platform': 'test',
                'platform_release': '1',
                'capabilities': ['agent.surface.inspect'],
                'tool_presence': {'python': True},
                'surface_inventory': {'surfaces': [{'provider': 'test'}]},
                'runtime': {
                    'source_commit': f'{node_id}-{i}',
                    'source_ref': 'feature/test',
                    'status': 'observed',
                },
                'observed_at': f'2026-08-29T08:00:{i % 60:02d}Z',
            },
        })


def test_concurrent_process_updates_leave_one_valid_registry(tmp_path: Path) -> None:
    path = tmp_path / 'nodes.json'
    registry = NodeRegistry(path)
    for node_id in ('node-a', 'node-b'):
        registry.register_manifest({
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': 'realm-test',
            'node_id': node_id,
            'role': 'client',
            'hostname': node_id,
            'platform': 'test',
            'platform_release': '1',
            'capabilities': [],
            'tool_presence': {},
            'surface_inventory': {},
            'runtime': {'source_commit': 'seed'},
        })

    workers = [
        mp.Process(target=_heartbeat_worker, args=(str(path), 'node-a', 40)),
        mp.Process(target=_heartbeat_worker, args=(str(path), 'node-b', 40)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0

    raw = path.read_text(encoding='utf-8')
    data = json.loads(raw)
    assert data['schema'] == 'agentos.node-registry/v0.1'
    assert set(data['nodes']) == {'node-a', 'node-b'}
    assert data['nodes']['node-a']['runtime']['source_commit'].startswith('node-a-')
    assert data['nodes']['node-b']['runtime']['source_commit'].startswith('node-b-')
    assert not list(tmp_path.glob('nodes.json.*.tmp'))


def test_heartbeat_manifest_is_one_transaction_and_preserves_runtime(tmp_path: Path) -> None:
    path = tmp_path / 'nodes.json'
    registry = NodeRegistry(path)
    entry = registry.record_heartbeat({
        'schema': 'agentos.node-heartbeat/v0.1',
        'realm_id': 'realm-test',
        'node_id': 'node-a',
        'status': 'online',
        'uptime_seconds': 12,
        'surface_count': 2,
        'manifest': {
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'node-a',
            'role': 'client',
            'hostname': 'node-a',
            'platform': 'test',
            'platform_release': '1',
            'capabilities': ['agent.surface.inspect'],
            'tool_presence': {},
            'surface_inventory': {},
            'runtime': {
                'source_commit': 'abc123',
                'source_ref': 'feature/realm-node-fabric-readiness',
                'status': 'observed',
            },
        },
    })
    assert entry['status'] == 'online'
    assert entry['runtime']['source_commit'] == 'abc123'
    assert json.loads(path.read_text(encoding='utf-8'))['nodes']['node-a']['runtime']['source_commit'] == 'abc123'
