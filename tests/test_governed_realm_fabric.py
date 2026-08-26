import json
from pathlib import Path

import pytest

from agent_core.governed_realm_fabric import GovernedRealmFabricStore


class DummyRegistry:
    def register_manifest(self, manifest):
        return manifest

    def record_heartbeat(self, heartbeat):
        return heartbeat


def make_store(tmp_path: Path) -> GovernedRealmFabricStore:
    path = tmp_path / 'fabric.json'
    store = GovernedRealmFabricStore(path=path, node_registry=DummyRegistry())
    data = store._empty()
    data['realm_id'] = 'realm-test'
    data['nodes']['node-a'] = {'node_id': 'node-a', 'token_hash': 'x', 'enrolled_at': 'now', 'last_seen_at': None, 'revoked_at': None}
    data['tasks']['node-a'] = []
    store.save(data)
    return store


def test_unknown_capability_cannot_enter_queue(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(PermissionError):
        store.queue_task('node-a', {'schema': 'agentos.node-task/v0.1', 'task_id': 't1', 'action': 'unknown.power'})


def test_network_fault_needs_recovery_armed(tmp_path):
    store = make_store(tmp_path)
    task = {'schema': 'agentos.node-task/v0.1', 'task_id': 't2', 'action': 'network.disconnect'}
    with pytest.raises(PermissionError):
        store.queue_task('node-a', task)

    task['governance'] = {'preflight_ok': True, 'recovery_armed': True}
    queued = store.queue_task('node-a', task)
    assert queued['governance_decision']['allowed'] is True
    assert queued['governance_decision']['recovery_required'] is True


def test_low_risk_inspection_can_queue(tmp_path):
    store = make_store(tmp_path)
    queued = store.queue_task('node-a', {'schema': 'agentos.node-task/v0.1', 'task_id': 't3', 'action': 'desktop.session.inspect'})
    assert queued['governance_decision']['allowed'] is True
