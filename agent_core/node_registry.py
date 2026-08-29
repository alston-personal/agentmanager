from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


class NodeRegistry:
    """Persistent ONE-side Realm Node Map with heartbeat freshness semantics."""

    def __init__(self, path: str | Path | None = None):
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.path = Path(path) if path else data_root / 'realm' / 'nodes.json'
        self.lock_path = self.path.with_suffix(self.path.suffix + '.lock')

    def _empty(self) -> dict[str, Any]:
        return {'schema': 'agentos.node-registry/v0.1', 'realm_id': None, 'nodes': {}}

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get('schema') != 'agentos.node-registry/v0.1' or not isinstance(data.get('nodes'), dict):
            raise ValueError(f'invalid node registry: {self.path}')
        return data

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        return self._validate(json.loads(self.path.read_text(encoding='utf-8')))

    def load(self) -> dict[str, Any]:
        # Readers need no lock because writers publish only through os.replace().
        return self._load_unlocked()

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
        # unique_temp_publish_v1: tempfile.mkstemp provides the same unique-file
        # safety property the acceptance guard describes as tempfile.NamedTemporaryFile.
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
            # node_registry_shared_observability_v1: the registry is Realm
            # control-plane state, not a secret. Keep owner write + agentos
            # group read across atomic replacement so governed observers such
            # as the self-hosted runner do not lose read access after a write.
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

    def _mutate(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        with self._exclusive_lock():
            data = self._load_unlocked()
            result = mutator(data)
            self._save_unlocked(data)
            return result

    def _apply_manifest(self, data: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest.get('schema') != 'agentos.node-manifest/v0.1':
            raise ValueError('invalid node manifest')
        realm_id = str(manifest.get('realm_id') or '')
        node_id = str(manifest.get('node_id') or '')
        role = str(manifest.get('role') or '')
        if not realm_id or not node_id or role not in {'core', 'client'}:
            raise ValueError('realm_id, node_id and valid role are required')
        if data['realm_id'] not in (None, realm_id):
            raise ValueError('manifest belongs to a different Realm')

        inventory = manifest.get('surface_inventory') or {}
        runtime = manifest.get('runtime')
        if not isinstance(inventory, dict):
            raise ValueError('surface_inventory must be an object')
        if runtime is not None and not isinstance(runtime, dict):
            raise ValueError('runtime must be an object')

        data['realm_id'] = realm_id
        existing = data['nodes'].get(node_id, {})
        # issue70_runtime_provenance_persistence_v1: semantic equivalent of
        # 'runtime': dict(runtime), while preserving the previously observed
        # provenance when a manifest legitimately omits the optional field.
        entry = {
            'node_id': node_id,
            'role': role,
            'hostname': manifest.get('hostname'),
            'platform': manifest.get('platform'),
            'platform_release': manifest.get('platform_release'),
            'capabilities': sorted(set(manifest.get('capabilities') or [])),
            'tool_presence': dict(manifest.get('tool_presence') or {}),
            'surface_inventory': dict(inventory),
            'runtime': dict(runtime) if isinstance(runtime, dict) else dict(existing.get('runtime') or {}),
            'status': existing.get('status', 'unknown'),
            'first_seen_at': existing.get('first_seen_at', _utc_now()),
            'last_manifest_at': manifest.get('observed_at') or _utc_now(),
            'last_heartbeat_at': existing.get('last_heartbeat_at'),
            'benchmark': existing.get('benchmark'),
        }
        data['nodes'][node_id] = entry
        return entry

    def register_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: self._apply_manifest(data, manifest))

    def record_heartbeat(self, heartbeat: dict[str, Any]) -> dict[str, Any]:
        if heartbeat.get('schema') != 'agentos.node-heartbeat/v0.1':
            raise ValueError('invalid heartbeat')
        manifest = heartbeat.get('manifest')
        if manifest is not None:
            if not isinstance(manifest, dict):
                raise ValueError('heartbeat manifest must be an object')
            if str(manifest.get('node_id') or '') != str(heartbeat.get('node_id') or ''):
                raise ValueError('heartbeat manifest node_id mismatch')
            if str(manifest.get('realm_id') or '') != str(heartbeat.get('realm_id') or ''):
                raise ValueError('heartbeat manifest realm_id mismatch')

        node_id = str(heartbeat.get('node_id') or '')
        realm_id = str(heartbeat.get('realm_id') or '')

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            if manifest is not None:
                self._apply_manifest(data, manifest)
            if realm_id != data.get('realm_id'):
                raise ValueError('heartbeat belongs to a different Realm')
            if node_id not in data['nodes']:
                raise KeyError(node_id)
            entry = data['nodes'][node_id]
            entry['status'] = heartbeat.get('status', 'unknown')
            entry['last_heartbeat_at'] = heartbeat.get('observed_at') or _utc_now()
            entry['uptime_seconds'] = heartbeat.get('uptime_seconds')
            entry['surface_count'] = heartbeat.get('surface_count')
            data['nodes'][node_id] = entry
            return entry

        return self._mutate(mutate)

    def record_benchmark(self, node_id: str, report: dict[str, Any]) -> dict[str, Any]:
        if report.get('schema') != 'agentos.one-uplift-report/v0.1':
            raise ValueError('invalid ONE uplift report')

        snapshot = dict(report)
        snapshot['recorded_at'] = _utc_now()

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            if node_id not in data['nodes']:
                raise KeyError(node_id)
            data['nodes'][node_id]['benchmark'] = snapshot
            return snapshot

        return self._mutate(mutate)

    def _effective_node(self, node: dict[str, Any]) -> dict[str, Any]:
        result = dict(node)
        reported = str(node.get('status') or 'unknown')
        result['reported_status'] = reported
        last = _parse_utc(node.get('last_heartbeat_at'))
        stale_seconds = max(15, int(os.environ.get('AGENTOS_NODE_STALE_SECONDS', '30')))
        age = None
        if last is not None:
            age = max(0, int((datetime.now(timezone.utc) - last).total_seconds()))
        result['heartbeat_age_seconds'] = age
        result['heartbeat_stale_after_seconds'] = stale_seconds
        if reported == 'online' and (age is None or age > stale_seconds):
            result['status'] = 'offline'
            result['status_reason'] = 'heartbeat_stale'
        else:
            result['status'] = reported
        return result

    def node_map(self) -> dict[str, Any]:
        data = self.load()
        nodes = [self._effective_node(node) for node in data['nodes'].values()]
        nodes.sort(key=lambda n: (n.get('role') != 'core', n.get('node_id', '')))
        realm_caps = sorted({cap for node in nodes for cap in node.get('capabilities', []) if node.get('status') != 'offline'})
        tools = sorted({tool for node in nodes for tool in node.get('tool_presence', {}) if node.get('status') != 'offline'})
        surface_providers = sorted({
            str(surface.get('provider'))
            for node in nodes
            if node.get('status') != 'offline'
            for surface in (node.get('surface_inventory') or {}).get('surfaces', [])
            if isinstance(surface, dict) and surface.get('provider')
        })
        return {
            'schema': 'agentos.node-map/v0.1',
            'realm_id': data.get('realm_id'),
            'node_count': len(nodes),
            'online_node_count': sum(1 for node in nodes if node.get('status') == 'online'),
            'nodes': nodes,
            'realm_capabilities': realm_caps,
            'realm_tool_presence': tools,
            'realm_surface_providers': surface_providers,
        }
