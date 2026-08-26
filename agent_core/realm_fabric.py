from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_core.node_registry import NodeRegistry


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class RealmFabricStore:
    """Persistent ONE-side state for Thin Client enrollment and task transport.

    Raw node credentials are never persisted. Only SHA-256 hashes are stored.
    The store is intentionally small and JSON-backed for the v0.1 closure.
    """

    def __init__(self, path: str | Path | None = None, *, node_registry: NodeRegistry | None = None):
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.path = Path(path) if path else data_root / 'realm' / 'fabric.json'
        self.node_registry = node_registry or NodeRegistry()

    def _empty(self) -> dict[str, Any]:
        return {
            'schema': 'agentos.realm-fabric/v0.1',
            'realm_id': None,
            'invites': {},
            'nodes': {},
            'tasks': {},
            'receipts': {},
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != 'agentos.realm-fabric/v0.1':
            raise ValueError(f'invalid Realm fabric store: {self.path}')
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.path)

    def initialize_realm(self, realm_id: str) -> dict[str, Any]:
        if not realm_id:
            raise ValueError('realm_id is required')
        data = self.load()
        if data['realm_id'] not in (None, realm_id):
            raise ValueError('Realm fabric already belongs to another Realm')
        data['realm_id'] = realm_id
        self.save(data)
        return {'realm_id': realm_id}

    def create_invite(self, *, expires_minutes: int = 10, label: str | None = None) -> dict[str, Any]:
        data = self.load()
        if not data.get('realm_id'):
            raise ValueError('initialize Realm before creating invites')
        invite_id = 'enr_' + secrets.token_hex(8)
        code = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        data['invites'][invite_id] = {
            'invite_id': invite_id,
            'code_hash': _hash_secret(code),
            'label': label,
            'created_at': _utc_now(),
            'expires_at': (now + timedelta(minutes=max(1, expires_minutes))).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'used_at': None,
        }
        self.save(data)
        return {
            'schema': 'agentos.enrollment-invite/v0.1',
            'realm_id': data['realm_id'],
            'invite_id': invite_id,
            'code': code,
            'expires_at': data['invites'][invite_id]['expires_at'],
            'label': label,
        }

    def enroll(self, *, invite_id: str, code: str, manifest: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        invite = data['invites'].get(invite_id)
        if not invite:
            raise PermissionError('unknown enrollment invite')
        if invite.get('used_at'):
            raise PermissionError('enrollment invite already used')
        if _parse_utc(invite['expires_at']) < datetime.now(timezone.utc):
            raise PermissionError('enrollment invite expired')
        if not secrets.compare_digest(invite['code_hash'], _hash_secret(code)):
            raise PermissionError('invalid enrollment code')
        if manifest.get('schema') != 'agentos.node-manifest/v0.1':
            raise ValueError('invalid node manifest')
        if manifest.get('realm_id') not in (None, '', data['realm_id']):
            raise ValueError('node manifest targets a different Realm')
        if manifest.get('role', 'client') != 'client':
            raise ValueError('external enrollment only accepts client role')
        node_id = str(manifest.get('node_id') or '').strip()
        if not node_id:
            raise ValueError('node_id is required')

        normalized = dict(manifest)
        normalized['realm_id'] = data['realm_id']
        normalized['role'] = 'client'
        node_entry = self.node_registry.register_manifest(normalized)

        token = secrets.token_urlsafe(32)
        data['nodes'][node_id] = {
            'node_id': node_id,
            'token_hash': _hash_secret(token),
            'enrolled_at': _utc_now(),
            'last_seen_at': None,
            'revoked_at': None,
        }
        invite['used_at'] = _utc_now()
        data['invites'][invite_id] = invite
        data['tasks'].setdefault(node_id, [])
        self.save(data)
        return {
            'schema': 'agentos.enrollment-result/v0.1',
            'realm_id': data['realm_id'],
            'node_id': node_id,
            'node_token': token,
            'node': node_entry,
        }

    def authenticate(self, node_id: str, token: str) -> dict[str, Any]:
        data = self.load()
        node = data['nodes'].get(node_id)
        if not node or node.get('revoked_at'):
            raise PermissionError('unknown or revoked node')
        if not secrets.compare_digest(node['token_hash'], _hash_secret(token)):
            raise PermissionError('invalid node credential')
        return node

    def record_heartbeat(self, heartbeat: dict[str, Any], token: str) -> dict[str, Any]:
        node_id = str(heartbeat.get('node_id') or '')
        self.authenticate(node_id, token)
        entry = self.node_registry.record_heartbeat(heartbeat)
        data = self.load()
        data['nodes'][node_id]['last_seen_at'] = heartbeat.get('observed_at') or _utc_now()
        self.save(data)
        return entry

    def queue_task(self, node_id: str, task: dict[str, Any]) -> dict[str, Any]:
        if task.get('schema') != 'agentos.node-task/v0.1':
            raise ValueError('invalid task schema')
        if not task.get('task_id'):
            raise ValueError('task_id is required')
        data = self.load()
        if node_id not in data['nodes']:
            raise KeyError(node_id)
        queued = dict(task)
        queued['queued_at'] = _utc_now()
        data['tasks'].setdefault(node_id, []).append(queued)
        self.save(data)
        return queued

    def pull_tasks(self, node_id: str, token: str, *, limit: int = 10) -> list[dict[str, Any]]:
        self.authenticate(node_id, token)
        data = self.load()
        queue = list(data['tasks'].get(node_id, []))
        take = queue[:max(1, min(limit, 50))]
        data['tasks'][node_id] = queue[len(take):]
        self.save(data)
        return take

    def record_receipt(self, receipt: dict[str, Any], token: str) -> dict[str, Any]:
        if receipt.get('schema') != 'agentos.node-receipt/v0.1':
            raise ValueError('invalid receipt schema')
        node_id = str(receipt.get('node_id') or '')
        self.authenticate(node_id, token)
        task_id = str(receipt.get('task_id') or '')
        if not task_id:
            raise ValueError('receipt task_id is required')
        data = self.load()
        data['receipts'][task_id] = {
            **receipt,
            'received_at': _utc_now(),
        }
        data['nodes'][node_id]['last_seen_at'] = _utc_now()
        self.save(data)
        return data['receipts'][task_id]

    def get_receipt(self, task_id: str) -> dict[str, Any] | None:
        return self.load()['receipts'].get(task_id)
