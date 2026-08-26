from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentos_node import interactive_desktop


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class NodeIdentity:
    realm_id: str
    node_id: str
    role: str = 'client'

    def __post_init__(self) -> None:
        if self.role not in {'core', 'client'}:
            raise ValueError('role must be core or client')
        if not self.realm_id or not self.node_id:
            raise ValueError('realm_id and node_id are required')


@dataclass
class ThinClientPolicy:
    allowed_executables: set[str] = field(default_factory=set)
    readable_roots: tuple[Path, ...] = field(default_factory=tuple)
    writable_roots: tuple[Path, ...] = field(default_factory=tuple)
    max_timeout_seconds: int = 300

    @staticmethod
    def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
        resolved = path.expanduser().resolve()
        for root in roots:
            base = root.expanduser().resolve()
            try:
                resolved.relative_to(base)
                return True
            except ValueError:
                continue
        return False

    def can_read(self, path: Path) -> bool:
        return self._inside(path, self.readable_roots)

    def can_write(self, path: Path) -> bool:
        return self._inside(path, self.writable_roots)

    def can_exec(self, executable: str) -> bool:
        name = Path(executable).name.lower()
        return name in {item.lower() for item in self.allowed_executables}


class ThinClient:
    COMMON_TOOLS = (
        'git', 'python', 'python3', 'node', 'npm', 'pnpm', 'docker', 'podman',
        'powershell', 'pwsh', 'ffmpeg', 'adb', 'xcodebuild', 'unity', 'Unity',
        'code', 'antigravity',
    )

    def __init__(self, identity: NodeIdentity, policy: ThinClientPolicy):
        self.identity = identity
        self.policy = policy
        self.hostname = socket.gethostname()
        self.started_at = _utc_now()

    def discover_tools(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for tool in self.COMMON_TOOLS:
            path = shutil.which(tool)
            if path:
                found[tool.lower()] = path
        return dict(sorted(found.items()))

    def capability_manifest(self) -> dict[str, Any]:
        tools = self.discover_tools()
        caps = ['context.harvest', 'process.inspect', 'tool.presence']
        if self.policy.allowed_executables:
            caps.append('shell.exec')
        if self.policy.readable_roots:
            caps.append('filesystem.read')
        if self.policy.writable_roots:
            caps.append('filesystem.write')
        if platform.system() == 'Windows':
            caps.extend([
                'desktop.session.inspect',
                'desktop.windows.inspect',
                'desktop.screenshot',
                'desktop.open_url',
                'desktop.mouse',
                'desktop.keyboard',
            ])
        return {
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': self.identity.realm_id,
            'node_id': self.identity.node_id,
            'role': self.identity.role,
            'hostname': self.hostname,
            'platform': platform.system(),
            'platform_release': platform.release(),
            'python_version': platform.python_version(),
            'observed_at': _utc_now(),
            'capabilities': sorted(caps),
            'tool_presence': tools,
            'workspace_roots': {
                'readable': [str(p.expanduser().resolve()) for p in self.policy.readable_roots],
                'writable': [str(p.expanduser().resolve()) for p in self.policy.writable_roots],
            },
        }

    def heartbeat(self) -> dict[str, Any]:
        return {
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': self.identity.realm_id,
            'node_id': self.identity.node_id,
            'role': self.identity.role,
            'status': 'online',
            'observed_at': _utc_now(),
            'uptime_seconds': max(0, int(time.time() - datetime.fromisoformat(self.started_at.replace('Z', '+00:00')).timestamp())),
            'capability_count': len(self.capability_manifest()['capabilities']),
        }

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        started = _utc_now()
        receipt: dict[str, Any] = {
            'schema': 'agentos.node-receipt/v0.1',
            'realm_id': self.identity.realm_id,
            'node_id': self.identity.node_id,
            'task_id': task.get('task_id'),
            'action': task.get('action'),
            'started_at': started,
            'completed_at': None,
            'ok': False,
            'cognition_ids_used': list(task.get('cognition_ids_used') or []),
        }
        try:
            if task.get('schema') != 'agentos.node-task/v0.1':
                raise ValueError('invalid task schema')
            action = task.get('action')
            if action == 'shell.exec':
                result = self._exec_shell(task)
            elif action == 'filesystem.read':
                result = self._read_file(task)
            elif action == 'filesystem.write':
                result = self._write_file(task)
            elif action == 'desktop.session.inspect':
                result = {'desktop': interactive_desktop.session_info()}
            elif action == 'desktop.windows.inspect':
                result = interactive_desktop.inspect_windows()
            elif action == 'desktop.open_url':
                result = interactive_desktop.open_url(str(task.get('url') or ''))
            elif action == 'desktop.screenshot':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else Path.cwd()
                result = interactive_desktop.screenshot(workspace, quality=int(task.get('quality') or 55))
            elif action == 'desktop.mouse':
                result = interactive_desktop.mouse(task)
            elif action == 'desktop.keyboard':
                result = interactive_desktop.keyboard(task)
            else:
                raise ValueError(f'unsupported action: {action}')
            receipt.update(result)
            receipt['ok'] = True
        except Exception as exc:
            receipt['error'] = f'{type(exc).__name__}: {exc}'
        receipt['completed_at'] = _utc_now()
        return receipt

    def _exec_shell(self, task: dict[str, Any]) -> dict[str, Any]:
        executable = str(task.get('executable') or '')
        argv = task.get('argv') or []
        if not executable or not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            raise ValueError('executable and string argv are required')
        if not self.policy.can_exec(executable):
            raise PermissionError(f'executable not allowlisted: {executable}')
        resolved = shutil.which(executable) or executable
        cwd_raw = task.get('cwd')
        cwd = Path(cwd_raw).expanduser().resolve() if cwd_raw else Path.cwd().resolve()
        if self.policy.readable_roots and not self.policy.can_read(cwd):
            raise PermissionError(f'cwd outside readable roots: {cwd}')
        timeout = min(int(task.get('timeout_seconds') or self.policy.max_timeout_seconds), self.policy.max_timeout_seconds)
        completed = subprocess.run([resolved, *argv], cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
        return {
            'returncode': completed.returncode,
            'stdout': completed.stdout[-30000:],
            'stderr': completed.stderr[-10000:],
            'execution': {'executable': resolved, 'argv': argv, 'cwd': str(cwd), 'timeout_seconds': timeout},
        }

    def _read_file(self, task: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(task.get('path') or '')).expanduser().resolve()
        if not self.policy.can_read(path):
            raise PermissionError(f'path outside readable roots: {path}')
        max_bytes = min(int(task.get('max_bytes') or 262144), 1048576)
        data = path.read_bytes()[:max_bytes]
        return {'path': str(path), 'bytes_read': len(data), 'content_utf8': data.decode('utf-8', errors='replace')}

    def _write_file(self, task: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(task.get('path') or '')).expanduser().resolve()
        if not self.policy.can_write(path):
            raise PermissionError(f'path outside writable roots: {path}')
        content = task.get('content_utf8')
        if not isinstance(content, str):
            raise ValueError('content_utf8 must be a string')
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.agentos.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)
        return {'path': str(path), 'bytes_written': len(content.encode('utf-8'))}


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
