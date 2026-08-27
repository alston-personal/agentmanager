from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

BRIDGE_SCHEMA = 'agentos.executor-bridge/v0.1'
REQUEST_SCHEMA = 'agentos.executor-request/v0.1'
RECEIPT_SCHEMA = 'agentos.executor-receipt/v0.1'


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def executor_bridge_root(executor_id: str) -> Path | None:
    key = 'AGENTOS_' + executor_id.upper().replace('-', '_') + '_EXECUTOR_BRIDGE'
    raw = os.environ.get(key)
    return Path(raw).expanduser() if raw else None


def describe_executor_bridge(
    executor_id: str,
    root: str | Path | None = None,
    *,
    stale_after_seconds: int = 15,
) -> dict[str, Any] | None:
    resolved = Path(root).expanduser() if root is not None else executor_bridge_root(executor_id)
    if resolved is None:
        return None
    descriptor = resolved / 'bridge.json'
    if not descriptor.exists():
        return {
            'schema': BRIDGE_SCHEMA,
            'executor_id': executor_id,
            'root': str(resolved),
            'ready': False,
            'status': 'unavailable',
            'reason': 'descriptor_missing',
            'capabilities': [],
        }
    try:
        payload = json.loads(descriptor.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get('schema') != BRIDGE_SCHEMA or str(payload.get('executor_id') or '') != executor_id:
        return None
    observed_at = str(payload.get('observed_at') or '')
    age_seconds: int | None = None
    stale = True
    if observed_at:
        try:
            age_seconds = max(0, int((datetime.now(timezone.utc) - _parse_utc(observed_at)).total_seconds()))
            stale = age_seconds > max(1, int(stale_after_seconds))
        except ValueError:
            stale = True
    ready = bool(payload.get('ready')) and not stale
    return {
        **payload,
        'root': str(resolved),
        'ready': ready,
        'status': 'available' if ready else 'unavailable',
        'reason': None if ready else ('heartbeat_stale' if stale else 'not_ready'),
        'heartbeat_age_seconds': age_seconds,
        'capabilities': sorted({str(x) for x in (payload.get('capabilities') or []) if str(x)}),
    }


class FileExecutorBridge:
    """Local file-backed request/receipt bridge between a Node Runtime and executor host.

    The filesystem ACL of the bridge root is the authority boundary. No network
    listener is opened. The executor host owns bridge.json and receipt production;
    the Node Runtime owns request production.
    """

    def __init__(self, executor_id: str, root: str | Path):
        self.executor_id = executor_id
        self.root = Path(root).expanduser()
        self.requests = self.root / 'requests'
        self.receipts = self.root / 'receipts'

    @classmethod
    def from_environment(cls, executor_id: str) -> 'FileExecutorBridge':
        root = executor_bridge_root(executor_id)
        if root is None:
            raise RuntimeError(f'no {executor_id} executor bridge configured')
        descriptor = describe_executor_bridge(executor_id, root)
        if not descriptor or not descriptor.get('ready'):
            reason = descriptor.get('reason') if descriptor else 'invalid_descriptor'
            raise RuntimeError(f'{executor_id} executor bridge is not ready: {reason}')
        return cls(executor_id, root)

    def request(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get('schema') != 'agentos.node-task/v0.1':
            raise ValueError('invalid node task schema')
        task_id = str(task.get('task_id') or '')
        if not task_id:
            raise ValueError('task_id is required')
        self.requests.mkdir(parents=True, exist_ok=True)
        request_id = 'executor-' + uuid.uuid4().hex
        request = {
            'schema': REQUEST_SCHEMA,
            'request_id': request_id,
            'executor_id': self.executor_id,
            'task': dict(task),
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
            raise ValueError('invalid executor bridge receipt')
        if str(payload.get('executor_id') or '') != self.executor_id:
            raise ValueError('executor bridge receipt belongs to another executor')
        return payload

    def execute(self, task: dict[str, Any], *, timeout_seconds: float = 30.0, poll_seconds: float = 0.1) -> dict[str, Any]:
        request = self.request(task)
        deadline = time.monotonic() + max(0.5, float(timeout_seconds))
        while time.monotonic() < deadline:
            receipt = self.receipt(str(request['request_id']))
            if receipt is not None:
                if not receipt.get('ok'):
                    raise RuntimeError(str(receipt.get('error') or 'executor failed'))
                result = receipt.get('result')
                if not isinstance(result, dict):
                    raise RuntimeError('executor result must be an object')
                return result
            time.sleep(max(0.02, float(poll_seconds)))
        raise TimeoutError(f'executor request timed out: {request["request_id"]}')


class FileExecutorHost:
    """Executor-side helper that publishes health and consumes bridge requests."""

    def __init__(
        self,
        executor_id: str,
        root: str | Path,
        *,
        capabilities: list[str] | tuple[str, ...],
        details_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.executor_id = executor_id
        self.root = Path(root).expanduser()
        self.requests = self.root / 'requests'
        self.receipts = self.root / 'receipts'
        self.capabilities = sorted(set(capabilities))
        self.details_provider = details_provider

    def publish_descriptor(self, *, ready: bool = True) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        details = dict(self.details_provider() if self.details_provider else {})
        payload = {
            'schema': BRIDGE_SCHEMA,
            'executor_id': self.executor_id,
            'ready': bool(ready),
            'observed_at': _utc_now(),
            'capabilities': self.capabilities,
            'security_boundary': 'filesystem_acl',
            'details': details,
        }
        target = self.root / 'bridge.json'
        tmp = target.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(tmp, target)
        return payload

    def serve_once(self, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> int:
        self.publish_descriptor(ready=True)
        self.requests.mkdir(parents=True, exist_ok=True)
        self.receipts.mkdir(parents=True, exist_ok=True)
        processed = 0
        for target in sorted(self.requests.glob('executor-*.json')):
            request_id = target.stem
            task: dict[str, Any] = {}
            try:
                request = json.loads(target.read_text(encoding='utf-8-sig'))
                if request.get('schema') != REQUEST_SCHEMA:
                    raise ValueError('invalid executor request schema')
                if str(request.get('executor_id') or '') != self.executor_id:
                    raise ValueError('executor request targets another executor')
                request_id = str(request.get('request_id') or '')
                task_raw = request.get('task')
                if not request_id or not isinstance(task_raw, dict):
                    raise ValueError('invalid executor request')
                task = task_raw
                result = handler(task)
                if not isinstance(result, dict):
                    raise ValueError('executor handler must return an object')
                receipt = {
                    'schema': RECEIPT_SCHEMA,
                    'request_id': request_id,
                    'executor_id': self.executor_id,
                    'task_id': task.get('task_id'),
                    'ok': True,
                    'result': result,
                    'completed_at': _utc_now(),
                }
            except Exception as exc:
                receipt = {
                    'schema': RECEIPT_SCHEMA,
                    'request_id': request_id,
                    'executor_id': self.executor_id,
                    'task_id': task.get('task_id'),
                    'ok': False,
                    'error': f'{type(exc).__name__}: {exc}',
                    'completed_at': _utc_now(),
                }
            receipt_target = self.receipts / f'{receipt["request_id"]}.json'
            tmp = receipt_target.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            os.replace(tmp, receipt_target)
            target.unlink(missing_ok=True)
            processed += 1
        return processed
