from __future__ import annotations

import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_core.realm_fabric import RealmFabricStore


ROOT = Path(__file__).resolve().parents[1]
REPAIR_PATH = ROOT / 'scripts' / 'repair_realm_fabric_truncated_tail.py'
spec = importlib.util.spec_from_file_location('repair_realm_fabric_truncated_tail', REPAIR_PATH)
assert spec and spec.loader
repair_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair_mod)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fabric_snapshot() -> dict:
    return {
        'schema': 'agentos.realm-fabric/v0.1',
        'realm_id': 'realm-alston',
        'invites': {},
        'join_requests': {},
        'nodes': {
            'node-a': {
                'node_id': 'node-a',
                'token_hash': 'x' * 64,
                'enrolled_at': '2026-09-09T00:00:00Z',
                'last_seen_at': None,
                'revoked_at': None,
            }
        },
        'tasks': {'node-a': []},
        'receipts': {},
    }


def test_concurrent_queue_mutations_do_not_lose_updates(tmp_path: Path):
    path = tmp_path / 'realm' / 'fabric.json'
    store = RealmFabricStore(path)
    store.save(fabric_snapshot())

    def enqueue(i: int) -> None:
        store.queue_task('node-a', {
            'schema': 'agentos.node-task/v0.1',
            'task_id': f'task-{i}',
            'action': 'bounded.test',
        })

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(enqueue, range(60)))

    data = store.load()
    tasks = data['tasks']['node-a']
    assert len(tasks) == 60
    assert {task['task_id'] for task in tasks} == {f'task-{i}' for i in range(60)}
    assert not list(path.parent.glob('fabric.json.*.tmp'))


def test_malformed_store_remains_fail_closed_in_normal_load(tmp_path: Path):
    path = tmp_path / 'fabric.json'
    prefix = json.dumps(fabric_snapshot(), sort_keys=True)
    path.write_text(prefix + '\npartial-tail', encoding='utf-8')
    with pytest.raises(json.JSONDecodeError):
        RealmFabricStore(path).load()


def test_hash_bound_repair_backs_up_original_and_restores_complete_prefix(tmp_path: Path):
    path = tmp_path / 'realm' / 'fabric.json'
    path.parent.mkdir(parents=True)
    prefix = json.dumps(fabric_snapshot(), sort_keys=True)
    tail = '\n  partial-tail-without-object-start'
    original = (prefix + tail).encode('utf-8')
    path.write_bytes(original)
    backup_dir = tmp_path / 'backups'

    result = repair_mod.repair_truncated_tail(
        path,
        expected_file_sha256=sha(original),
        expected_prefix_sha256=sha(prefix.encode('utf-8')),
        backup_dir=backup_dir,
    )

    assert result['ok'] is True
    assert result['realm_id'] == 'realm-alston'
    assert result['credential_exposed'] is False
    backup = Path(result['backup_path'])
    assert backup.read_bytes() == original
    assert (backup.stat().st_mode & 0o777) == 0o600
    assert json.loads(path.read_text(encoding='utf-8')) == fabric_snapshot()


def test_repair_refuses_if_full_file_hash_changed(tmp_path: Path):
    path = tmp_path / 'fabric.json'
    prefix = json.dumps(fabric_snapshot(), sort_keys=True)
    original = (prefix + '\npartial').encode('utf-8')
    path.write_bytes(original)
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='file_sha_mismatch'):
        repair_mod.repair_truncated_tail(
            path,
            expected_file_sha256='0' * 64,
            expected_prefix_sha256=sha(prefix.encode('utf-8')),
            backup_dir=tmp_path / 'backups',
        )
    assert path.read_bytes() == before


def test_repair_refuses_complete_second_snapshot(tmp_path: Path):
    path = tmp_path / 'fabric.json'
    first = json.dumps(fabric_snapshot(), sort_keys=True)
    second_data = fabric_snapshot()
    second_data['receipts'] = {'task-x': {'status': 'completed'}}
    second = json.dumps(second_data, sort_keys=True)
    original = (first + '\n' + second).encode('utf-8')
    path.write_bytes(original)
    with pytest.raises(RuntimeError, match='complete_second_snapshot_refused'):
        repair_mod.repair_truncated_tail(
            path,
            expected_file_sha256=sha(original),
            expected_prefix_sha256=sha(first.encode('utf-8')),
            backup_dir=tmp_path / 'backups',
        )


def test_repair_refuses_prefix_hash_mismatch_without_backup(tmp_path: Path):
    path = tmp_path / 'fabric.json'
    prefix = json.dumps(fabric_snapshot(), sort_keys=True)
    original = (prefix + '\npartial').encode('utf-8')
    path.write_bytes(original)
    backup_dir = tmp_path / 'backups'
    with pytest.raises(RuntimeError, match='prefix_sha_mismatch'):
        repair_mod.repair_truncated_tail(
            path,
            expected_file_sha256=sha(original),
            expected_prefix_sha256='f' * 64,
            backup_dir=backup_dir,
        )
    assert not backup_dir.exists()
