from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from agent_core.node_registry import NodeRegistry


T = TypeVar('T')


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _user_code() -> str:
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    raw = ''.join(secrets.choice(alphabet) for _ in range(8))
    return raw[:4] + '-' + raw[4:]


class RealmFabricStore:
    """Persistent ONE-side state for Thin Client enrollment and task transport.

    Raw node credentials and device-flow claim secrets are never persisted.
    Only SHA-256 hashes are stored. v0.1 keeps the store JSON-backed while the
    protocol and governance boundaries stabilize.

    All state-changing operations are serialized across threads and processes.
    One exclusive transaction owns load -> mutate -> fsync -> atomic replace, so
    concurrent heartbeat/task/receipt requests cannot lose each other's updates
    or share one temporary pathname. Arbitrary malformed JSON remains fail-closed;
    repair of a historical truncated store is an explicit, hash-bound operation.
    """

    _process_lock = threading.RLock()

    def __init__(self, path: str | Path | None = None, *, node_registry: NodeRegistry | None = None):
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.path = Path(path) if path else data_root / 'realm' / 'fabric.json'
        self.lock_path = self.path.with_suffix(self.path.suffix + '.lock')
        self.node_registry = node_registry or NodeRegistry()

    def _empty(self) -> dict[str, Any]:
        return {
            'schema': 'agentos.realm-fabric/v0.1',
            'realm_id': None,
            'invites': {},
            'join_requests': {},
            'nodes': {},
            'tasks': {},
            'receipts': {},
        }

    def _validate(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict) or data.get('schema') != 'agentos.realm-fabric/v0.1':
            raise ValueError(f'invalid Realm fabric store: {self.path}')
        for field in ('invites', 'join_requests', 'nodes', 'tasks', 'receipts'):
            value = data.setdefault(field, {})
            if not isinstance(value, dict):
                raise ValueError(f'invalid Realm fabric field {field}: {self.path}')
        return data

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        # Deliberately strict. Historical corruption must be repaired through the
        # explicit hash-bound repair tool, never silently guessed in normal reads.
        return self._validate(json.loads(self.path.read_text(encoding='utf-8')))

    def load(self) -> dict[str, Any]:
        # Published files are replaced atomically, so readers never need to hold
        # the writer lock after the historical store has been repaired.
        return self._load_unlocked()

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._process_lock:
            with self.lock_path.open('a+', encoding='utf-8') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self._validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + '.',
            suffix='.tmp',
            dir=str(self.path.parent),
            text=True,
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o640)
            os.replace(tmp, self.path)
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if tmp.exists():
                tmp.unlink()

    def save(self, data: dict[str, Any]) -> None:
        with self._exclusive_lock():
            self._save_unlocked(data)

    def _mutate(self, mutator: Callable[[dict[str, Any]], T]) -> T:
        with self._exclusive_lock():
            data = self._load_unlocked()
            result = mutator(data)
            self._save_unlocked(data)
            return result

    @staticmethod
    def _authenticate_data(data: dict[str, Any], node_id: str, token: str) -> dict[str, Any]:
        node = data['nodes'].get(node_id)
        if not node or node.get('revoked_at'):
            raise PermissionError('unknown or revoked node')
        if not secrets.compare_digest(str(node.get('token_hash') or ''), _hash_secret(token)):
            raise PermissionError('invalid node credential')
        return node

    def initialize_realm(self, realm_id: str) -> dict[str, Any]:
        if not realm_id:
            raise ValueError('realm_id is required')

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            if data['realm_id'] not in (None, realm_id):
                raise ValueError('Realm fabric already belongs to another Realm')
            data['realm_id'] = realm_id
            return {'realm_id': realm_id}

        return self._mutate(mutate)

    def _normalize_manifest(self, manifest: dict[str, Any], realm_id: str) -> dict[str, Any]:
        if manifest.get('schema') != 'agentos.node-manifest/v0.1':
            raise ValueError('invalid node manifest')
        if manifest.get('realm_id') not in (None, '', 'pending', realm_id):
            raise ValueError('node manifest targets a different Realm')
        if manifest.get('role', 'client') != 'client':
            raise ValueError('external enrollment only accepts client role')
        node_id = str(manifest.get('node_id') or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        normalized = dict(manifest)
        normalized['realm_id'] = realm_id
        normalized['role'] = 'client'
        normalized['node_id'] = node_id
        return normalized

    def _register_node(self, data: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
        node_id = normalized['node_id']
        node_entry = self.node_registry.register_manifest(normalized)
        token = secrets.token_urlsafe(32)
        data['nodes'][node_id] = {
            'node_id': node_id,
            'token_hash': _hash_secret(token),
            'enrolled_at': _utc_now(),
            'last_seen_at': None,
            'revoked_at': None,
        }
        data['tasks'].setdefault(node_id, [])
        return {
            'schema': 'agentos.enrollment-result/v0.1',
            'realm_id': data['realm_id'],
            'node_id': node_id,
            'node_token': token,
            'node': node_entry,
        }

    def create_invite(self, *, expires_minutes: int = 10, label: str | None = None) -> dict[str, Any]:
        holder: dict[str, Any] = {}

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
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
            holder['code'] = code
            return {
                'schema': 'agentos.enrollment-invite/v0.1',
                'realm_id': data['realm_id'],
                'invite_id': invite_id,
                'code': code,
                'expires_at': data['invites'][invite_id]['expires_at'],
                'label': label,
            }

        return self._mutate(mutate)

    def enroll(self, *, invite_id: str, code: str, manifest: dict[str, Any]) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            invite = data['invites'].get(invite_id)
            if not invite:
                raise PermissionError('unknown enrollment invite')
            if invite.get('used_at'):
                raise PermissionError('enrollment invite already used')
            if _parse_utc(invite['expires_at']) < datetime.now(timezone.utc):
                raise PermissionError('enrollment invite expired')
            if not secrets.compare_digest(invite['code_hash'], _hash_secret(code)):
                raise PermissionError('invalid enrollment code')
            normalized = self._normalize_manifest(manifest, data['realm_id'])
            result = self._register_node(data, normalized)
            invite['used_at'] = _utc_now()
            data['invites'][invite_id] = invite
            return result

        return self._mutate(mutate)

    def request_join(self, *, manifest: dict[str, Any], expires_minutes: int = 10) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            realm_id = str(data.get('realm_id') or '')
            if not realm_id:
                raise ValueError('initialize Realm before requesting enrollment')
            normalized = self._normalize_manifest(manifest, realm_id)
            node_id = normalized['node_id']
            if node_id in data['nodes'] and not data['nodes'][node_id].get('revoked_at'):
                raise ValueError('node_id already enrolled')

            request_id = 'join_' + secrets.token_hex(10)
            claim_secret = secrets.token_urlsafe(32)
            user_code = _user_code()
            existing_codes = {str(v.get('user_code') or '') for v in data['join_requests'].values()}
            while user_code in existing_codes:
                user_code = _user_code()
            now = datetime.now(timezone.utc)
            expires_at = (now + timedelta(minutes=max(1, min(int(expires_minutes), 30)))).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
            data['join_requests'][request_id] = {
                'request_id': request_id,
                'user_code': user_code,
                'claim_secret_hash': _hash_secret(claim_secret),
                'manifest': normalized,
                'created_at': _utc_now(),
                'expires_at': expires_at,
                'approved_at': None,
                'denied_at': None,
                'claimed_at': None,
            }
            return {
                'schema': 'agentos.join-request/v0.1',
                'realm_id': realm_id,
                'request_id': request_id,
                'user_code': user_code,
                'claim_secret': claim_secret,
                'expires_at': expires_at,
                'node_id': node_id,
                'status': 'pending',
            }

        return self._mutate(mutate)

    def _find_join(self, data: dict[str, Any], selector: str) -> tuple[str, dict[str, Any]]:
        selector = str(selector or '').strip().upper()
        if not selector:
            raise ValueError('join request selector is required')
        for request_id, entry in data['join_requests'].items():
            if request_id.upper() == selector or str(entry.get('user_code') or '').upper() == selector:
                return request_id, entry
        raise KeyError(selector)

    def approve_join(self, selector: str) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            request_id, entry = self._find_join(data, selector)
            if entry.get('claimed_at'):
                raise ValueError('join request already claimed')
            if entry.get('denied_at'):
                raise ValueError('join request was denied')
            if _parse_utc(entry['expires_at']) < datetime.now(timezone.utc):
                raise PermissionError('join request expired')
            entry['approved_at'] = entry.get('approved_at') or _utc_now()
            data['join_requests'][request_id] = entry
            return {
                'schema': 'agentos.join-approval/v0.1',
                'ok': True,
                'request_id': request_id,
                'user_code': entry['user_code'],
                'node_id': entry['manifest']['node_id'],
                'approved_at': entry['approved_at'],
            }

        return self._mutate(mutate)

    def join_status(self, *, request_id: str, claim_secret: str) -> dict[str, Any]:
        data = self.load()
        entry = data['join_requests'].get(request_id)
        if not entry or not secrets.compare_digest(str(entry.get('claim_secret_hash') or ''), _hash_secret(claim_secret)):
            raise PermissionError('invalid join request credential')
        if entry.get('claimed_at'):
            return {'schema': 'agentos.join-status/v0.1', 'status': 'claimed', 'request_id': request_id}
        if entry.get('denied_at'):
            return {'schema': 'agentos.join-status/v0.1', 'status': 'denied', 'request_id': request_id}
        if _parse_utc(entry['expires_at']) < datetime.now(timezone.utc):
            return {'schema': 'agentos.join-status/v0.1', 'status': 'expired', 'request_id': request_id}
        return {
            'schema': 'agentos.join-status/v0.1',
            'status': 'approved' if entry.get('approved_at') else 'pending',
            'request_id': request_id,
            'user_code': entry['user_code'],
            'node_id': entry['manifest']['node_id'],
        }

    def claim_join(self, *, request_id: str, claim_secret: str) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            entry = data['join_requests'].get(request_id)
            if not entry or not secrets.compare_digest(str(entry.get('claim_secret_hash') or ''), _hash_secret(claim_secret)):
                raise PermissionError('invalid join request credential')
            if entry.get('claimed_at'):
                raise PermissionError('join request already claimed')
            if entry.get('denied_at'):
                raise PermissionError('join request denied')
            if _parse_utc(entry['expires_at']) < datetime.now(timezone.utc):
                raise PermissionError('join request expired')
            if not entry.get('approved_at'):
                return {'schema': 'agentos.join-status/v0.1', 'status': 'pending', 'request_id': request_id}

            result = self._register_node(data, dict(entry['manifest']))
            entry['claimed_at'] = _utc_now()
            data['join_requests'][request_id] = entry
            return {'status': 'enrolled', **result}

        return self._mutate(mutate)

    def authenticate(self, node_id: str, token: str) -> dict[str, Any]:
        return self._authenticate_data(self.load(), node_id, token)

    def record_heartbeat(self, heartbeat: dict[str, Any], token: str) -> dict[str, Any]:
        node_id = str(heartbeat.get('node_id') or '')
        observed_at = heartbeat.get('observed_at') or _utc_now()
        # NodeRegistry has its own independent lock. Authenticate the Fabric and
        # reserve this Fabric mutation first, then update the NodeRegistry while
        # this transaction remains serialized. A failed registry update prevents
        # publication of a new Fabric last_seen_at.
        with self._exclusive_lock():
            data = self._load_unlocked()
            self._authenticate_data(data, node_id, token)
            entry = self.node_registry.record_heartbeat(heartbeat)
            data['nodes'][node_id]['last_seen_at'] = observed_at
            self._save_unlocked(data)
            return entry

    def queue_task(self, node_id: str, task: dict[str, Any]) -> dict[str, Any]:
        if task.get('schema') != 'agentos.node-task/v0.1':
            raise ValueError('invalid task schema')
        if not task.get('task_id'):
            raise ValueError('task_id is required')

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            if node_id not in data['nodes']:
                raise KeyError(node_id)
            queued = dict(task)
            queued['queued_at'] = _utc_now()
            data['tasks'].setdefault(node_id, []).append(queued)
            return queued

        return self._mutate(mutate)

    def pull_tasks(self, node_id: str, token: str, *, limit: int = 10) -> list[dict[str, Any]]:
        def mutate(data: dict[str, Any]) -> list[dict[str, Any]]:
            self._authenticate_data(data, node_id, token)
            queue = list(data['tasks'].get(node_id, []))
            take = queue[:max(1, min(limit, 50))]
            data['tasks'][node_id] = queue[len(take):]
            return take

        return self._mutate(mutate)

    def record_receipt(self, receipt: dict[str, Any], token: str) -> dict[str, Any]:
        if receipt.get('schema') != 'agentos.node-receipt/v0.1':
            raise ValueError('invalid receipt schema')
        node_id = str(receipt.get('node_id') or '')
        task_id = str(receipt.get('task_id') or '')
        if not task_id:
            raise ValueError('receipt task_id is required')

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            self._authenticate_data(data, node_id, token)
            stored = {**receipt, 'received_at': _utc_now()}
            data['receipts'][task_id] = stored
            data['nodes'][node_id]['last_seen_at'] = _utc_now()
            return stored

        return self._mutate(mutate)

    def get_receipt(self, task_id: str) -> dict[str, Any] | None:
        return self.load()['receipts'].get(task_id)
