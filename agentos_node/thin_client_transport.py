from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


@dataclass
class ClientConfig:
    one_url: str
    realm_id: str
    node_id: str
    node_token: str
    poll_seconds: float = 5.0

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


class ThinClientTransport:
    def __init__(self, client: ThinClient, config: ClientConfig | None = None):
        self.client = client
        self.config = config

    @staticmethod
    def _request(url: str, *, method: str = 'GET', body: dict[str, Any] | None = None, token: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
        headers = {'Accept': 'application/json', 'User-Agent': 'AgentOS-ThinClient/0.1'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'ONE HTTP {exc.code}: {detail}') from exc
        if not isinstance(payload, dict):
            raise RuntimeError('ONE response must be a JSON object')
        return payload

    @classmethod
    def request_enrollment(
        cls,
        *,
        one_url: str,
        node_id: str,
        policy: ThinClientPolicy,
        expires_minutes: int = 10,
    ) -> dict[str, Any]:
        normalized = one_url.rstrip('/')
        provisional = ThinClient(NodeIdentity(realm_id='pending', node_id=node_id), policy)
        manifest = provisional.capability_manifest()
        manifest['realm_id'] = ''
        result = cls._request(
            normalized + '/v1/join/request',
            method='POST',
            body={'manifest': manifest, 'expires_minutes': max(1, min(int(expires_minutes), 30))},
        )
        if not result.get('ok'):
            raise RuntimeError(f'enrollment request failed: {result}')
        return result

    @classmethod
    def wait_for_approval(
        cls,
        *,
        one_url: str,
        request_id: str,
        claim_secret: str,
        config_path: str | Path,
        poll_seconds: float = 2.0,
        timeout_seconds: int = 600,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> ClientConfig:
        normalized = one_url.rstrip('/')
        deadline = time.monotonic() + max(10, int(timeout_seconds))
        last_status = None
        while time.monotonic() < deadline:
            status = cls._request(
                normalized + '/v1/join/status',
                method='POST',
                body={'request_id': request_id, 'claim_secret': claim_secret},
            )
            if status.get('status') != last_status and on_status:
                on_status(status)
            last_status = status.get('status')
            if status.get('status') in {'denied', 'expired', 'claimed'}:
                raise RuntimeError(f'enrollment ended with status={status.get("status")}')
            if status.get('status') == 'approved':
                result = cls._request(
                    normalized + '/v1/join/claim',
                    method='POST',
                    body={'request_id': request_id, 'claim_secret': claim_secret},
                )
                if result.get('status') == 'enrolled' and result.get('node_token'):
                    config = ClientConfig(
                        one_url=normalized,
                        realm_id=str(result['realm_id']),
                        node_id=str(result['node_id']),
                        node_token=str(result['node_token']),
                    )
                    config.save(config_path)
                    return config
            time.sleep(max(1.0, float(poll_seconds)))
        raise TimeoutError('enrollment approval timed out')

    @classmethod
    def enroll_device(
        cls,
        *,
        one_url: str,
        node_id: str,
        policy: ThinClientPolicy,
        config_path: str | Path,
        expires_minutes: int = 10,
        timeout_seconds: int = 600,
        on_request: Callable[[dict[str, Any]], None] | None = None,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> ClientConfig:
        request = cls.request_enrollment(
            one_url=one_url,
            node_id=node_id,
            policy=policy,
            expires_minutes=expires_minutes,
        )
        if on_request:
            # claim_secret remains process-local; callers should display user_code only.
            on_request({k: v for k, v in request.items() if k != 'claim_secret'})
        return cls.wait_for_approval(
            one_url=one_url,
            request_id=str(request['request_id']),
            claim_secret=str(request['claim_secret']),
            config_path=config_path,
            timeout_seconds=timeout_seconds,
            on_status=on_status,
        )

    @classmethod
    def enroll(
        cls,
        *,
        one_url: str,
        invite_id: str,
        code: str,
        node_id: str,
        policy: ThinClientPolicy,
        config_path: str | Path,
    ) -> ClientConfig:
        normalized = one_url.rstrip('/')
        provisional = ThinClient(NodeIdentity(realm_id='pending', node_id=node_id), policy)
        manifest = provisional.capability_manifest()
        manifest['realm_id'] = ''
        result = cls._request(
            normalized + '/v1/enroll',
            method='POST',
            body={'invite_id': invite_id, 'code': code, 'manifest': manifest},
        )
        if not result.get('ok'):
            raise RuntimeError(f'enrollment failed: {result}')
        config = ClientConfig(
            one_url=normalized,
            realm_id=str(result['realm_id']),
            node_id=str(result['node_id']),
            node_token=str(result['node_token']),
        )
        config.save(config_path)
        return config

    def health(self) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        return self._request(self.config.one_url + '/v1/health')

    def heartbeat(self) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        return self._request(
            self.config.one_url + '/v1/heartbeat',
            method='POST',
            body=self.client.heartbeat(),
            token=self.config.node_token,
        )

    def pull_tasks(self) -> list[dict[str, Any]]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        query = urllib.parse.urlencode({'node_id': self.config.node_id})
        result = self._request(
            self.config.one_url + '/v1/tasks?' + query,
            token=self.config.node_token,
        )
        return list(result.get('tasks') or [])

    def submit_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        return self._request(
            self.config.one_url + '/v1/receipts',
            method='POST',
            body=receipt,
            token=self.config.node_token,
        )

    def run_once(self) -> list[dict[str, Any]]:
        self.heartbeat()
        receipts: list[dict[str, Any]] = []
        for task in self.pull_tasks():
            receipt = self.client.execute(task)
            self.submit_receipt(receipt)
            receipts.append(receipt)
        return receipts

    def run_forever(self) -> None:
        if not self.config:
            raise RuntimeError('client is not enrolled')
        delay = max(1.0, float(self.config.poll_seconds))
        while True:
            try:
                self.run_once()
            except Exception as exc:
                print(f'[agentos-client] transport error: {exc}', flush=True)
            time.sleep(delay)


def build_client(config: ClientConfig, policy: ThinClientPolicy) -> ThinClientTransport:
    client = ThinClient(NodeIdentity(config.realm_id, config.node_id), policy)
    return ThinClientTransport(client, config)
