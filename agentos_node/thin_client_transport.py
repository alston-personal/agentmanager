from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
