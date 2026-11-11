from __future__ import annotations

import hashlib
import json
import os
import time
import threading
import urllib.error
import socket
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agentos_node.onboarding import build_join_regression_report
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


def _client_home() -> Path:
    root = os.environ.get('AGENTOS_CLIENT_HOME')
    return Path(root).expanduser() if root else (Path.home() / '.agentos')


def _heartbeat_lease_path() -> Path:
    return _client_home() / 'heartbeat-lease.json'


def _liveness_lease_path() -> Path:
    return _client_home() / 'daemon-liveness.json'


def _receipt_spool_dir() -> Path:
    return _client_home() / 'pending-receipts'


def _spool_receipt(receipt: dict[str, Any]) -> Path:
    task_id = str(receipt.get('task_id') or 'unknown')
    digest = hashlib.sha256(task_id.encode('utf-8')).hexdigest()
    directory = _receipt_spool_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{digest}.json'
    tmp = target.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, target)
    return target


def _write_liveness_lease(config: 'ClientConfig') -> None:
    target = _liveness_lease_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': 'agentos.node-daemon-liveness/v0.1',
        'realm_id': config.realm_id,
        'node_id': config.node_id,
        'recorded_at_unix': int(time.time()),
        'pid': os.getpid(),
    }
    tmp = target.with_suffix(target.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, target)


def _write_heartbeat_lease(config: 'ClientConfig') -> None:
    target = _heartbeat_lease_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': 'agentos.node-heartbeat-lease/v0.1',
        'realm_id': config.realm_id,
        'node_id': config.node_id,
        'one_url': config.one_url,
        'recorded_at_unix': int(time.time()),
    }
    tmp = target.with_suffix(target.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, target)


@dataclass
class ClientConfig:
    one_url: str
    realm_id: str
    node_id: str
    node_token: str
    poll_seconds: float = 0.25
    task_wait_seconds: float = 20.0

    @classmethod
    def load(cls, path: str | Path) -> 'ClientConfig':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls(**data)

    def save(self, path: str | Path) -> None:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass


_TENANT_REALM_ID = re.compile(r"realm-u-[0-9a-f]{24}\Z")


def device_join_base(one_url: str, realm_id: str | None = None) -> str:
    """Route a device request to its explicitly selected Realm, not realm-alston."""
    normalized = one_url.rstrip('/')
    if realm_id is None:
        return normalized + '/v1/join'
    if not _TENANT_REALM_ID.fullmatch(realm_id):
        raise ValueError('invalid_tenant_realm_id')
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.scheme != 'https' or parsed.hostname != 'agentos.milkcat.org' or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('tenant_join_requires_agentos_origin')
    return normalized + '/v1/realms/' + realm_id + '/join'


def node_runtime_endpoint(config: ClientConfig, action: str) -> str:
    """Tenant node runtime is isolated from legacy /v1 on the default ONE."""
    if _TENANT_REALM_ID.fullmatch(config.realm_id):
        return device_join_base(config.one_url, config.realm_id).rsplit('/join', 1)[0] + '/' + action
    return config.one_url.rstrip('/') + '/v1/' + action


class ThinClientTransport:
    def __init__(self, client: ThinClient, config: ClientConfig | None = None):
        self.client = client
        self.config = config

    @staticmethod
    def _request(
        url: str,
        *,
        method: str = 'GET',
        body: dict[str, Any] | None = None,
        token: str | None = None,
        timeout: float = 15.0,
        retries: int = 0,
    ) -> dict[str, Any]:
        headers = {'Accept': 'application/json', 'User-Agent': 'AgentOS-ThinClient/0.1'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    payload = json.loads(response.read().decode('utf-8'))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode('utf-8', errors='replace')
                raise RuntimeError(f'ONE HTTP {exc.code}: {detail}') from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                if attempt >= max(0, int(retries)):
                    raise RuntimeError(f'ONE transport timeout: {type(exc).__name__}: {exc}') from exc
                attempt += 1
                time.sleep(min(5.0, 0.5 * (2 ** (attempt - 1))))
        if not isinstance(payload, dict):
            raise RuntimeError('ONE response must be a JSON object')
        return payload

    @classmethod
    def request_enrollment(cls, *, one_url: str, node_id: str, policy: ThinClientPolicy, expires_minutes: int = 10, realm_id: str | None = None) -> dict[str, Any]:
        normalized = one_url.rstrip('/')
        provisional = ThinClient(NodeIdentity(realm_id='pending', node_id=node_id), policy)
        manifest = provisional.capability_manifest()
        manifest['realm_id'] = realm_id or ''
        result = cls._request(device_join_base(normalized, realm_id) + '/request', method='POST', body={'manifest': manifest, 'expires_minutes': max(1, min(int(expires_minutes), 30))})
        if not result.get('ok'):
            raise RuntimeError(f'enrollment request failed: {result}')
        return result

    @classmethod
    def wait_for_approval(cls, *, one_url: str, request_id: str, claim_secret: str, config_path: str | Path, poll_seconds: float = 2.0, timeout_seconds: int = 600, on_status: Callable[[dict[str, Any]], None] | None = None, realm_id: str | None = None) -> ClientConfig:
        normalized = one_url.rstrip('/')
        deadline = time.monotonic() + max(10, int(timeout_seconds))
        last_status = None
        while time.monotonic() < deadline:
            status = cls._request(device_join_base(normalized, realm_id) + '/status', method='POST', body={'request_id': request_id, 'claim_secret': claim_secret})
            if status.get('status') != last_status and on_status:
                on_status(status)
            last_status = status.get('status')
            if status.get('status') in {'denied', 'expired', 'claimed'}:
                raise RuntimeError(f'enrollment ended with status={status.get("status")}')
            if status.get('status') == 'approved':
                result = cls._request(device_join_base(normalized, realm_id) + '/claim', method='POST', body={'request_id': request_id, 'claim_secret': claim_secret})
                if result.get('status') == 'enrolled' and result.get('node_token'):
                    config = ClientConfig(one_url=normalized, realm_id=str(result['realm_id']), node_id=str(result['node_id']), node_token=str(result['node_token']))
                    config.save(config_path)
                    return config
            time.sleep(max(1.0, float(poll_seconds)))
        raise TimeoutError('enrollment approval timed out')

    @classmethod
    def enroll_device(cls, *, one_url: str, node_id: str, policy: ThinClientPolicy, config_path: str | Path, expires_minutes: int = 10, timeout_seconds: int = 600, on_request: Callable[[dict[str, Any]], None] | None = None, on_status: Callable[[dict[str, Any]], None] | None = None, realm_id: str | None = None) -> ClientConfig:
        request = cls.request_enrollment(one_url=one_url, node_id=node_id, policy=policy, expires_minutes=expires_minutes, realm_id=realm_id)
        if on_request:
            on_request({k: v for k, v in request.items() if k != 'claim_secret'})
        return cls.wait_for_approval(one_url=one_url, request_id=str(request['request_id']), claim_secret=str(request['claim_secret']), config_path=config_path, timeout_seconds=timeout_seconds, on_status=on_status, realm_id=realm_id)

    @classmethod
    def enroll(cls, *, one_url: str, invite_id: str, code: str, node_id: str, policy: ThinClientPolicy, config_path: str | Path) -> ClientConfig:
        normalized = one_url.rstrip('/')
        provisional = ThinClient(NodeIdentity(realm_id='pending', node_id=node_id), policy)
        manifest = provisional.capability_manifest()
        manifest['realm_id'] = ''
        result = cls._request(normalized + '/v1/enroll', method='POST', body={'invite_id': invite_id, 'code': code, 'manifest': manifest})
        if not result.get('ok'):
            raise RuntimeError(f'enrollment failed: {result}')
        config = ClientConfig(one_url=normalized, realm_id=str(result['realm_id']), node_id=str(result['node_id']), node_token=str(result['node_token']))
        config.save(config_path)
        return config

    def health(self) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        url = node_runtime_endpoint(self.config, 'health')
        if _TENANT_REALM_ID.fullmatch(self.config.realm_id):
            url += '?' + urllib.parse.urlencode({'node_id': self.config.node_id})
        return self._request(url, token=self.config.node_token, retries=2)

    def heartbeat(self) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        heartbeat = self.client.heartbeat()
        result = self._request(
            node_runtime_endpoint(self.config, 'heartbeat'),
            method='POST',
            body=heartbeat,
            token=self.config.node_token,
            retries=2,
        )
        _write_heartbeat_lease(self.config)
        self._record_local_heartbeat(heartbeat)
        return result

    def _record_local_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        root = os.environ.get('AGENTOS_CLIENT_HOME')
        if not root:
            return
        target = Path(root) / 'heartbeat.json'
        payload = {
            'schema': 'agentos.local-heartbeat/v0.1',
            'realm_id': self.config.realm_id if self.config else None,
            'node_id': self.config.node_id if self.config else None,
            'observed_at': heartbeat.get('observed_at'),
            'recorded_at_epoch': time.time(),
        }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + '.tmp')
            tmp.write_text(json.dumps(payload, ensure_ascii=False) + '\n', encoding='utf-8')
            os.replace(tmp, target)
        except OSError as exc:
            # Local liveness evidence must never make a successful Realm heartbeat fail.
            print(f'[agentos-client] local heartbeat marker error: {exc}', flush=True)

    def bootstrap(self) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        query = urllib.parse.urlencode({'node_id': self.config.node_id})
        return self._request(node_runtime_endpoint(self.config, 'bootstrap') + '?' + query, token=self.config.node_token, retries=2)

    def resolve(self, project: str, *, intent: str = 'continue') -> dict[str, Any]:
        """Resolve canonical project continuation state through ONE.

        The client does not inspect GitHub, local workspaces, application identity
        registries, or memory files to reconstruct project truth. ONE/AgentOS is
        the authority for composing the continuation envelope.
        """
        if not self.config:
            raise RuntimeError('client is not enrolled')
        project = str(project or '').strip()
        if not project:
            raise ValueError('project is required')
        body = {
            'schema': 'agentos.resolve-request/v1',
            'node_id': self.config.node_id,
            'intent': intent,
            'project': project,
        }
        return self._request(
            node_runtime_endpoint(self.config, 'resolve'),
            method='POST',
            body=body,
            token=self.config.node_token,
        )

    def submit_benchmark(self, report: dict[str, Any]) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        return self._request(node_runtime_endpoint(self.config, 'benchmark'), method='POST', body=report, token=self.config.node_token)

    def _complete_regression(self, before_manifest: dict[str, Any], *, report_kind: str, completion_schema: str, lifecycle: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        heartbeat = self.heartbeat()
        after_manifest = self.client.capability_manifest()
        bootstrap = self.bootstrap()
        report = build_join_regression_report(
            realm_id=self.config.realm_id,
            node_id=self.config.node_id,
            before_manifest=before_manifest,
            after_manifest=after_manifest,
            bootstrap=bootstrap,
            report_kind=report_kind,
            lifecycle=lifecycle,
        )
        persisted = self.submit_benchmark(report)
        return {
            'schema': completion_schema,
            'realm_id': self.config.realm_id,
            'node_id': self.config.node_id,
            'heartbeat': heartbeat,
            'bootstrap': bootstrap,
            'lifecycle': lifecycle,
            'regression': report,
            'benchmark_persisted': bool(persisted.get('ok')),
            'node_ready': bool(report.get('node_ready')) and bool(persisted.get('ok')),
        }

    def complete_join(self, before_manifest: dict[str, Any], *, lifecycle: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._complete_regression(before_manifest, report_kind='join-regression', completion_schema='agentos.join-completion/v0.1', lifecycle=lifecycle)

    def verify_readiness(self, *, lifecycle: dict[str, Any] | None = None) -> dict[str, Any]:
        """Verify an already-enrolled Node against current discovery, lifecycle, and inherited Realm state."""
        baseline = self.client.capability_manifest()
        return self._complete_regression(baseline, report_kind='readiness-regression', completion_schema='agentos.node-readiness/v0.1', lifecycle=lifecycle)

    def pull_tasks(self, *, wait_seconds: float | None = None) -> list[dict[str, Any]]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        wait = self.config.task_wait_seconds if wait_seconds is None else wait_seconds
        wait = max(0.0, min(float(wait), 25.0))
        query = urllib.parse.urlencode({'node_id': self.config.node_id, 'wait_seconds': f'{wait:.3f}'})
        result = self._request(
            node_runtime_endpoint(self.config, 'tasks') + '?' + query,
            token=self.config.node_token,
            timeout=max(15.0, wait + 5.0),
        )
        return list(result.get('tasks') or [])

    def submit_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        return self._request(node_runtime_endpoint(self.config, 'receipts'), method='POST', body=receipt, token=self.config.node_token)

    def _persist_and_submit_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        spool_path = _spool_receipt(receipt)
        result = self.submit_receipt(receipt)
        try:
            spool_path.unlink()
        except FileNotFoundError:
            pass
        return result

    def _flush_spooled_receipts(self) -> int:
        directory = _receipt_spool_dir()
        if not directory.is_dir():
            return 0
        flushed = 0
        quarantine = directory / 'quarantine'
        for path in sorted(directory.glob('*.json')):
            try:
                # utf-8-sig tolerates BOM-producing writers (notably Windows
                # PowerShell 5.1 Set-Content -Encoding UTF8) while remaining
                # compatible with canonical UTF-8 spool files.
                receipt = json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(receipt, dict):
                    raise ValueError('receipt spool payload must be an object')
                self.submit_receipt(receipt)
                path.unlink()
                flushed += 1
            except Exception as exc:
                quarantine.mkdir(parents=True, exist_ok=True)
                target = quarantine / path.name
                try:
                    os.replace(path, target)
                except OSError:
                    target = path
                print(
                    f'[agentos-client] quarantined malformed/unflushable receipt '
                    f'path={target} error={type(exc).__name__}: {exc}',
                    flush=True,
                )
        return flushed

    def run_once(self) -> list[dict[str, Any]]:
        self.heartbeat()
        receipts: list[dict[str, Any]] = []
        for task in self.pull_tasks():
            receipt = self.client.execute(task)
            self._persist_and_submit_receipt(receipt)
            receipts.append(receipt)
        return receipts

    def _liveness_forever(self, delay: float) -> None:
        interval = max(1.0, min(2.0, delay))
        while True:
            try:
                if self.config:
                    _write_liveness_lease(self.config)
            except Exception as exc:
                print(f'[agentos-client] liveness error: {exc}', flush=True)
            time.sleep(interval)

    def _heartbeat_forever(self, delay: float) -> None:
        while True:
            try:
                self.heartbeat()
            except Exception as exc:
                print(f'[agentos-client] heartbeat error: {exc}', flush=True)
            time.sleep(delay)

    def _execute_task_bounded(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute one task behind a daemon-thread deadline supervisor.

        A provider call can wedge even when its inner subprocess timeout is
        correctly configured. Never let such a call permanently monopolize the
        Thin Client task loop. On deadline, persist a synthetic receipt first,
        then terminate the daemon so Task Scheduler/watchdog can recover it.
        """
        requested = int(task.get('timeout_seconds') or self.client.policy.max_timeout_seconds)
        action_timeout = max(1, min(requested, self.client.policy.max_timeout_seconds))
        deadline_seconds = action_timeout + 15
        done = threading.Event()
        box: dict[str, Any] = {}

        def worker() -> None:
            try:
                box['receipt'] = self.client.execute(task)
            except BaseException as exc:
                box['fatal'] = f'{type(exc).__name__}: {exc}'
            finally:
                done.set()

        thread = threading.Thread(
            target=worker,
            name=f"agentos-task-{str(task.get('task_id') or 'unknown')[:32]}",
            daemon=True,
        )
        thread.start()
        if done.wait(deadline_seconds):
            receipt = box.get('receipt')
            if isinstance(receipt, dict):
                return receipt
            now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            return {
                'schema': 'agentos.node-receipt/v0.1',
                'realm_id': self.config.realm_id if self.config else self.client.identity.realm_id,
                'node_id': self.config.node_id if self.config else self.client.identity.node_id,
                'task_id': task.get('task_id'),
                'action': task.get('action'),
                'started_at': now,
                'completed_at': now,
                'ok': False,
                'cognition_ids_used': list(task.get('cognition_ids_used') or []),
                'error': str(box.get('fatal') or 'task worker exited without receipt'),
            }

        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        receipt = {
            'schema': 'agentos.node-receipt/v0.1',
            'realm_id': self.config.realm_id if self.config else self.client.identity.realm_id,
            'node_id': self.config.node_id if self.config else self.client.identity.node_id,
            'task_id': task.get('task_id'),
            'action': task.get('action'),
            'started_at': now,
            'completed_at': now,
            'ok': False,
            'cognition_ids_used': list(task.get('cognition_ids_used') or []),
            'error': f'task executor deadline exceeded after {deadline_seconds}s; daemon restart required',
            'executor_supervisor': {
                'deadline_seconds': deadline_seconds,
                'action_timeout_seconds': action_timeout,
                'recovery': 'restart_daemon',
            },
        }
        _spool_receipt(receipt)
        print(
            f"[agentos-client] task deadline exceeded task_id={task.get('task_id')} "
            f"deadline_seconds={deadline_seconds}; receipt spooled; exiting for recovery",
            flush=True,
        )
        raise SystemExit(75)

    def run_forever(self) -> None:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        delay = max(1.0, float(self.config.poll_seconds))
        liveness_thread = threading.Thread(
            target=self._liveness_forever,
            args=(delay,),
            name='agentos-liveness',
            daemon=True,
        )
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_forever,
            args=(delay,),
            name='agentos-heartbeat',
            daemon=True,
        )
        liveness_thread.start()
        heartbeat_thread.start()
        while True:
            try:
                flushed = self._flush_spooled_receipts()
                if flushed:
                    print(f'[agentos-client] flushed_receipts={flushed}', flush=True)
                receipts: list[dict[str, Any]] = []
                for task in self.pull_tasks():
                    receipt = self._execute_task_bounded(task)
                    self._persist_and_submit_receipt(receipt)
                    receipts.append(receipt)
            except Exception as exc:
                print(f'[agentos-client] transport error: {exc}', flush=True)
                time.sleep(retry_delay)


def build_client(config: ClientConfig, policy: ThinClientPolicy) -> ThinClientTransport:
    client = ThinClient(NodeIdentity(config.realm_id, config.node_id), policy)
    return ThinClientTransport(client, config)
