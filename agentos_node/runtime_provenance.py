from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any


SCHEMA = 'agentos.thin-client-runtime/v0.1'


def default_path() -> Path:
    override = str(os.environ.get('AGENTOS_RUNTIME_PROVENANCE') or '').strip()
    if override:
        return Path(override).expanduser()
    if platform.system() == 'Windows':
        local = str(os.environ.get('LOCALAPPDATA') or '').strip()
        if local:
            return Path(local) / 'AgentOS' / 'runtime-provenance.json'
    return Path.home() / '.local' / 'share' / 'agentos' / 'runtime-provenance.json'


def observe_runtime() -> dict[str, Any]:
    path = default_path()
    payload: dict[str, Any] = {'schema': SCHEMA, 'provenance_path': str(path)}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError) as exc:
            payload['status'] = 'invalid'
            payload['error'] = f'{type(exc).__name__}: {exc}'
            return payload
        if not isinstance(data, dict) or data.get('schema') != SCHEMA:
            payload['status'] = 'invalid'
            payload['error'] = 'runtime provenance schema mismatch'
            return payload
        payload.update(data)
        payload['provenance_path'] = str(path)
        payload['status'] = 'observed'
        return payload

    source_ref = str(os.environ.get('AGENTOS_RUNTIME_SOURCE_REF') or '').strip()
    source_commit = str(os.environ.get('AGENTOS_RUNTIME_SOURCE_COMMIT') or '').strip()
    if source_ref:
        payload['source_ref'] = source_ref
    if source_commit:
        payload['source_commit'] = source_commit
    payload['status'] = 'environment' if source_ref or source_commit else 'unknown'
    return payload
