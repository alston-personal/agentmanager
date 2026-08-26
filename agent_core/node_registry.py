from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class NodeRegistry:
    """Persistent ONE-side Realm Node Map.

    Logic lives in agentmanager; mutable Realm state lives outside the source
    repository under AGENT_DATA_ROOT by default.
    """

    def __init__(self, path: str | Path | None = None):
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.path = Path(path) if path else data_root / 'realm' / 'nodes.json'

    def _empty(self) -> dict[str, Any]:
        return {'schema': 'agentos.node-registry/v0.1', 'realm_id': None, 'nodes': {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != 'agentos.node-registry/v0.1' or not isinstance(data.get('nodes'), dict):
            raise ValueError(f'invalid node registry: {self.path}')
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.path)

    def register_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get('schema') != 'agentos.node-manifest/v0.1':
            raise ValueError('invalid node manifest')
        realm_id = str(manifest.get('realm_id') or '')
        node_id = str(manifest.get('node_id') or '')
        role = str(manifest.get('role') or '')
        if not realm_id or not node_id or role not in {'core', 'client'}:
            raise ValueError('realm_id, node_id and valid role are required')

        data = self.load()
        if data['realm_id'] not in (None, realm_id):
            raise ValueError('manifest belongs to a different Realm')
        data['realm_id'] = realm_id
        existing = data['nodes'].get(node_id, {})
        entry = {
            'node_id': node_id,
            'role': role,
            'hostname': manifest.get('hostname'),
            'platform': manifest.get('platform'),
            'platform_release': manifest.get('platform_release'),
            'capabilities': sorted(set(manifest.get('capabilities') or [])),
            'tool_presence': dict(manifest.get('tool_presence') or {}),
            'status': existing.get('status', 'unknown'),
            'first_seen_at': existing.get('first_seen_at', _utc_now()),
            'last_manifest_at': manifest.get('observed_at') or _utc_now(),
            'last_heartbeat_at': existing.get('last_heartbeat_at'),
            'benchmark': existing.get('benchmark'),
        }
        data['nodes'][node_id] = entry
        self.save(data)
        return entry

    def record_heartbeat(self, heartbeat: dict[str, Any]) -> dict[str, Any]:
        if heartbeat.get('schema') != 'agentos.node-heartbeat/v0.1':
            raise ValueError('invalid heartbeat')
        data = self.load()
        node_id = str(heartbeat.get('node_id') or '')
        realm_id = str(heartbeat.get('realm_id') or '')
        if realm_id != data.get('realm_id'):
            raise ValueError('heartbeat belongs to a different Realm')
        if node_id not in data['nodes']:
            raise KeyError(node_id)
        entry = data['nodes'][node_id]
        entry['status'] = heartbeat.get('status', 'unknown')
        entry['last_heartbeat_at'] = heartbeat.get('observed_at') or _utc_now()
        entry['uptime_seconds'] = heartbeat.get('uptime_seconds')
        data['nodes'][node_id] = entry
        self.save(data)
        return entry

    def record_benchmark(self, node_id: str, report: dict[str, Any]) -> dict[str, Any]:
        if report.get('schema') != 'agentos.one-uplift-report/v0.1':
            raise ValueError('invalid ONE uplift report')
        data = self.load()
        if node_id not in data['nodes']:
            raise KeyError(node_id)
        snapshot = dict(report)
        snapshot['recorded_at'] = _utc_now()
        data['nodes'][node_id]['benchmark'] = snapshot
        self.save(data)
        return snapshot

    def node_map(self) -> dict[str, Any]:
        data = self.load()
        nodes = sorted(data['nodes'].values(), key=lambda n: (n.get('role') != 'core', n.get('node_id', '')))
        realm_caps = sorted({cap for node in nodes for cap in node.get('capabilities', []) if node.get('status') != 'offline'})
        tools = sorted({tool for node in nodes for tool in node.get('tool_presence', {})})
        return {
            'schema': 'agentos.node-map/v0.1',
            'realm_id': data.get('realm_id'),
            'node_count': len(nodes),
            'nodes': nodes,
            'realm_capabilities': realm_caps,
            'realm_tool_presence': tools,
        }
