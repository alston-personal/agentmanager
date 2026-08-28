from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class RuntimeOTAPolicyStore:
    """Persistent Realm desired-state for Thin Client OTA convergence."""

    SCHEMA = 'agentos.runtime-ota-policy/v0.1'

    def __init__(self, path: str | Path | None = None):
        data_root = Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.path = Path(path) if path else data_root / 'realm' / 'runtime-ota.json'

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                'schema': self.SCHEMA,
                'desired_source_ref': None,
                'desired_source_commit': None,
                'auto_converge': False,
                'updated_at': None,
            }
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != self.SCHEMA:
            raise ValueError(f'invalid runtime OTA policy: {self.path}')
        return data

    def set_desired(self, *, source_commit: str, source_ref: str = 'feature/realm-node-fabric-readiness', auto_converge: bool = False) -> dict[str, Any]:
        source_commit = str(source_commit or '').strip()
        source_ref = str(source_ref or '').strip()
        if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be a 40-character lowercase git SHA')
        if source_ref not in {'main', 'feature/realm-node-fabric-readiness'}:
            raise ValueError('source_ref is not allowlisted')
        payload = {
            'schema': self.SCHEMA,
            'desired_source_ref': source_ref,
            'desired_source_commit': source_commit,
            'auto_converge': bool(auto_converge),
            'updated_at': _utc_now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.path)
        return payload

    @staticmethod
    def annotate_node(node: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        result = dict(node)
        runtime = dict(result.get('runtime') or {})
        desired = str(policy.get('desired_source_commit') or '')
        observed = str(runtime.get('source_commit') or '')
        result['runtime'] = runtime
        if not desired:
            result['runtime_status'] = 'unmanaged'
        elif not observed:
            result['runtime_status'] = 'unknown'
        elif observed == desired:
            result['runtime_status'] = 'converged'
        else:
            result['runtime_status'] = 'drifted'
        result['desired_runtime_commit'] = desired or None
        return result
