from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from agentos_node.session_bridge import describe_bridge


@dataclass(frozen=True)
class Surface:
    surface_id: str
    kind: str
    provider: str
    executable: str | None
    running: bool
    capabilities: tuple[str, ...]
    attachable: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['capabilities'] = list(self.capabilities)
        payload['metadata'] = dict(self.metadata or {})
        return payload


KNOWN_SURFACES: tuple[dict[str, Any], ...] = (
    {'provider': 'antigravity', 'executables': ('antigravity',), 'kind': 'ide-agent', 'capabilities': ('agent.chat', 'code.edit')},
    {'provider': 'vscode', 'executables': ('code', 'code-insiders'), 'kind': 'ide', 'capabilities': ('ide.inspect', 'code.edit')},
    {'provider': 'cursor', 'executables': ('cursor',), 'kind': 'ide-agent', 'capabilities': ('agent.chat', 'code.edit')},
    {'provider': 'claude-code', 'executables': ('claude',), 'kind': 'agent-runtime', 'capabilities': ('agent.chat', 'code.edit')},
    {'provider': 'codex', 'executables': ('codex',), 'kind': 'agent-runtime', 'capabilities': ('agent.chat', 'code.edit')},
    {'provider': 'gemini', 'executables': ('gemini',), 'kind': 'agent-runtime', 'capabilities': ('agent.chat',)},
)


def _running_process_names() -> set[str]:
    names: set[str] = set()
    try:
        if platform.system() == 'Windows':
            completed = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], text=True, capture_output=True, timeout=5, check=False)
            for line in completed.stdout.splitlines():
                if not line.strip():
                    continue
                first = line.split(',', 1)[0].strip().strip('"')
                if first:
                    names.add(first.lower())
                    names.add(os.path.splitext(first.lower())[0])
        else:
            completed = subprocess.run(['ps', '-A', '-o', 'comm='], text=True, capture_output=True, timeout=5, check=False)
            for line in completed.stdout.splitlines():
                name = os.path.basename(line.strip()).lower()
                if name:
                    names.add(name)
                    names.add(os.path.splitext(name)[0])
    except (OSError, subprocess.SubprocessError):
        return set()
    return names


def discover_surfaces(*, process_names: Iterable[str] | None = None, which=shutil.which) -> dict[str, Any]:
    running = {str(x).lower() for x in (process_names if process_names is not None else _running_process_names())}
    surfaces: list[Surface] = []

    for spec in KNOWN_SURFACES:
        executable_path = None
        executable_name = None
        for candidate in spec['executables']:
            path = which(candidate)
            if path:
                executable_path = path
                executable_name = candidate
                break

        aliases = {str(x).lower() for x in spec['executables']}
        is_running = bool(aliases & running)
        if executable_path is None and not is_running:
            continue

        provider = str(spec['provider'])
        bridge = describe_bridge(provider)
        capabilities = list(spec['capabilities'])
        if bridge and bridge.get('ready'):
            capabilities.extend(bridge.get('capabilities') or [])

        surfaces.append(Surface(
            surface_id=f'{spec["kind"]}:{provider}',
            kind=str(spec['kind']),
            provider=provider,
            executable=executable_path,
            running=is_running,
            capabilities=tuple(sorted(set(capabilities))),
            attachable=bool(bridge and bridge.get('ready') and 'agent.session.attach' in (bridge.get('capabilities') or [])),
            metadata={
                'executable_name': executable_name,
                'session_bridge': bridge,
            },
        ))

    payload = [surface.to_dict() for surface in sorted(surfaces, key=lambda item: item.surface_id)]
    return {
        'schema': 'agentos.surface-inventory/v0.1',
        'surfaces': payload,
        'surface_count': len(payload),
        'capabilities': sorted({cap for item in payload for cap in item['capabilities']}),
        'providers': sorted({item['provider'] for item in payload}),
    }
