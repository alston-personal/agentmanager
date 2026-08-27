from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRIDGE_SCHEMA = 'agentos.session-bridge/v0.1'
SESSION_INDEX_SCHEMA = 'agentos.session-index/v0.1'
REQUEST_SCHEMA = 'agentos.session-request/v0.1'
RECEIPT_SCHEMA = 'agentos.session-receipt/v0.1'

_OPERATION_CAPS = {
    'discover': 'agent.session.discover',
    'snapshot': 'agent.session.inspect',
    'harvest': 'agent.context.harvest',
    'attach': 'agent.session.attach',
    'inject': 'agent.context.inject',
    'handoff': 'agent.session.handoff',
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def bridge_root(provider: str) -> Path | None:
    key = 'AGENTOS_' + provider.upper().replace('-', '_') + '_BRIDGE'
    raw = os.environ.get(key)
    return Path(raw).expanduser() if raw else None


def describe_bridge(provider: str) -> dict[str, Any] | None:
    root = bridge_root(provider)
    if root is None:
        return None
    descriptor = root / 'bridge.json'
    if not descriptor.exists():
        return {
            'schema': BRIDGE_SCHEMA,
            'provider': provider,
            'root': str(root),
            'operations': [],
            'capabilities': [],
            'ready': False,
        }
    try:
        payload = json.loads(descriptor.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get('schema') != BRIDGE_SCHEMA or str(payload.get('provider') or '') != provider:
        return None
    operations = sorted({str(op) for op in (payload.get('operations') or []) if str(op) in _OPERATION_CAPS})
    return {
        **payload,
        'root': str(root),
        'operations': operations,
        'capabilities': sorted({_OPERATION_CAPS[op] for op in operations}),
        'ready': bool(payload.get('ready', True)),
    }


class FileSessionBridge:
    """Portable provider bridge between AgentOS Node and an IDE/agent integration.

    The provider side owns bridge.json and sessions.json and consumes requests.
    AgentOS never scrapes private IDE state or claims chat access merely because a
    process is running.
    """

    def __init__(self, provider: str, root: str | Path):
        self.provider = provider
        self.root = Path(root).expanduser()
        self.requests = self.root / 'requests'
        self.receipts = self.root / 'receipts'

    @classmethod
    def from_environment(cls, provider: str) -> 'FileSessionBridge':
        root = bridge_root(provider)
        if root is None:
            raise RuntimeError(f'no {provider} session bridge configured')
        descriptor = describe_bridge(provider)
        if not descriptor or not descriptor.get('ready'):
            raise RuntimeError(f'{provider} session bridge is not ready')
        return cls(provider, root)

    def _require_operation(self, operation: str) -> None:
        descriptor = describe_bridge(self.provider)
        if not descriptor or operation not in (descriptor.get('operations') or []):
            raise PermissionError(f'{self.provider} bridge does not authorize operation: {operation}')

    def discover(self) -> dict[str, Any]:
        self._require_operation('discover')
        target = self.root / 'sessions.json'
        if not target.exists():
            return {'schema': SESSION_INDEX_SCHEMA, 'provider': self.provider, 'sessions': []}
        payload = json.loads(target.read_text(encoding='utf-8-sig'))
        if payload.get('schema') != SESSION_INDEX_SCHEMA or str(payload.get('provider') or '') != self.provider:
            raise ValueError('invalid session index')
        sessions = payload.get('sessions') or []
        if not isinstance(sessions, list):
            raise ValueError('sessions must be a list')
        return payload

    def request(self, operation: str, *, session_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_operation(operation)
        self.requests.mkdir(parents=True, exist_ok=True)
        request_id = 'session-' + uuid.uuid4().hex
        request = {
            'schema': REQUEST_SCHEMA,
            'request_id': request_id,
            'provider': self.provider,
            'operation': operation,
            'session_id': session_id,
            'payload': dict(payload or {}),
            'created_at': _utc_now(),
        }
        target = self.requests / f'{request_id}.json'
        tmp = target.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(tmp, target)
        return request

    def receipt(self, request_id: str) -> dict[str, Any] | None:
        target = self.receipts / f'{request_id}.json'
        if not target.exists():
            return None
        payload = json.loads(target.read_text(encoding='utf-8-sig'))
        if payload.get('schema') != RECEIPT_SCHEMA or str(payload.get('request_id') or '') != request_id:
            raise ValueError('invalid session bridge receipt')
        return payload
