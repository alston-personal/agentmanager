from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.request
import socket

from agentos_node import interactive_desktop
from agentos_node import desktop_demo
from agentos_node.agent_surfaces import discover_surfaces
from agentos_node.runtime_provenance import observe_runtime
from agentos_node.session_bridge import FileSessionBridge
from agentos_node.node_adapter import AdapterRegistry, load_configured_adapters


def _linux_gui_worker_capabilities() -> list[str]:
    if platform.system() != 'Linux':
        return []
    root = Path.home() / '.local' / 'share' / 'agentos' / 'gui-worker'
    cap = root / 'capability.json'
    if not cap.is_file():
        return []
    try:
        doc=json.loads(cap.read_text(encoding='utf-8'))
        if doc.get('schema')!='agentos.gui-worker/v1':
            return []
        with urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=1.5) as r:
            cdp=json.load(r)
        if not cdp.get('webSocketDebuggerUrl'):
            return []
        s=socket.create_connection(('127.0.0.1',6080),timeout=1.5)
        s.close()
    except Exception:
        return []
    allowed={'browser.gui','browser.cdp','browser.persistent_profile','desktop.remote_view'}
    return sorted(allowed.intersection(set(doc.get('capabilities') or [])))


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
    employee_wake_root: Path | None = None
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
        'code', 'cursor', 'antigravity', 'claude', 'codex', 'gemini',
    )

    def __init__(self, identity: NodeIdentity, policy: ThinClientPolicy, adapters: AdapterRegistry | None = None):
        self.identity = identity
        self.policy = policy
        self.adapters = adapters if adapters is not None else AdapterRegistry(load_configured_adapters())
        self.hostname = socket.gethostname()
        self.started_at = _utc_now()

    def discover_tools(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for tool in self.COMMON_TOOLS:
            path = shutil.which(tool)
            if path:
                found[tool.lower()] = path
        return dict(sorted(found.items()))

    def surface_inventory(self) -> dict[str, Any]:
        return discover_surfaces()

    @staticmethod
    def _safe_git_remote_identity(value: str) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        match = re.search(r'github\.com(?::|/)([^/\s]+/[^/\s]+?)(?:\.git)?    def capability_manifest(self) -> dict[str, Any]:
        tools = self.discover_tools()
        surface_inventory = self.surface_inventory()
        caps = [
            'context.harvest', 'process.inspect', 'tool.presence', 'agent.surface.inspect',
            'agent.executor.discover', 'agent.executor.reconcile',
        ]
        if self.policy.readable_roots:
            caps.append('agent.project.inspect')
        if platform.system() == 'Linux':
            caps.extend(['node.ssh.inspect', 'node.ssh.recover', 'node.runner.inspect', 'node.runner.recover'])
        caps.extend(surface_inventory.get('capabilities') or [])

        # Session bridge capabilities are provider-authorized and must be
        # advertised only when a configured bridge is actually ready.
        # This keeps Node discovery aligned with what execute() can really do.
        for provider in ('antigravity', 'gemini', 'claude-code', 'codex', 'cursor', 'vscode'):
            try:
                from agentos_node.session_bridge import describe_bridge
                descriptor = describe_bridge(provider)
            except Exception:
                descriptor = None
            if descriptor and descriptor.get('ready'):
                caps.extend(descriptor.get('capabilities') or [])
                # Receipts are part of the same governed bridge surface.
                caps.append('agent.session.receipt')
        if self.policy.allowed_executables:
            caps.append('shell.exec')
        if self.policy.readable_roots:
            caps.append('filesystem.read')
        if self.policy.writable_roots:
            caps.append('filesystem.write')
        if self.policy.employee_wake_root is not None:
            caps.append('agent.employee.wake.deliver')
        if platform.system() == 'Windows':
            caps.extend([
                'desktop.session.inspect', 'desktop.windows.inspect', 'desktop.screenshot',
                'desktop.open_url', 'desktop.mouse', 'desktop.keyboard',
                'desktop.windows.tile', 'desktop.demo.start', 'desktop.demo.stage', 'desktop.demo.stop',
            ])
        elif platform.system() == 'Darwin':
            caps.extend(['desktop.open_url', 'node.runtime.converge'])
            try:
                from agentos_node.social.threads_gui_client import capability_ready as threads_gui_read_ready
                if threads_gui_read_ready():
                    caps.append('threads.gui.read')
            except Exception:
                pass
        elif platform.system() == 'Linux':
            caps.extend(_linux_gui_worker_capabilities())
        caps.extend(self.adapters.capabilities())
        from agentos_node.executor_reconcile import discover_executor_inventory
        executor_inventory = discover_executor_inventory(probe_health=False)
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
            'capabilities': sorted(set(caps)),
            'tool_presence': tools,
            'surface_inventory': surface_inventory,
            'executor_inventory': executor_inventory,
            'adapters': self.adapters.describe(),
            'runtime': observe_runtime(),
            'workspace_roots': {
                'readable': [str(p.expanduser().resolve()) for p in self.policy.readable_roots],
                'writable': [str(p.expanduser().resolve()) for p in self.policy.writable_roots],
            },
        }

    def heartbeat(self) -> dict[str, Any]:
        manifest = self.capability_manifest()
        return {
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': self.identity.realm_id,
            'node_id': self.identity.node_id,
            'role': self.identity.role,
            'status': 'online',
            'observed_at': _utc_now(),
            'uptime_seconds': max(0, int(time.time() - datetime.fromisoformat(self.started_at.replace('Z', '+00:00')).timestamp())),
            'capability_count': len(manifest['capabilities']),
            'surface_count': int((manifest.get('surface_inventory') or {}).get('surface_count') or 0),
            'manifest': manifest,
        }

    def _session_bridge(self, task: dict[str, Any]) -> FileSessionBridge:
        provider = str(task.get('provider') or '').strip()
        if not provider:
            raise ValueError('provider is required for session bridge action')
        return FileSessionBridge.from_environment(provider)

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
            elif action == 'agent.employee.wake.deliver':
                if self.policy.employee_wake_root is None:
                    raise PermissionError('employee_wake_inbox_not_configured')
                from agentos_node.employee_wake_inbox import deliver_employee_wake
                result = deliver_employee_wake(
                    task,
                    self.policy.employee_wake_root,
                    expected_node_id=self.identity.node_id,
                )
            elif action == 'agent.surface.inspect':
                result = {'surface_inventory': self.surface_inventory()}
            elif action == 'agent.executor.discover':
                from agentos_node.executor_reconcile import discover_executor_inventory
                result = {'executor_inventory': discover_executor_inventory(probe_health=False)}
            elif action == 'agent.executor.reconcile':
                from agentos_node.executor_reconcile import reconcile_executor_adoption
                result = reconcile_executor_adoption(node_id=self.identity.node_id)
            elif action == 'agent.project.inspect':
                result = self._inspect_project(task)
            elif action == 'process.inspect':
                result = self._inspect_processes(task)
            elif action == 'node.ssh.inspect':
                result = self._inspect_ssh()
            elif action == 'node.ssh.recover':
                result = self._recover_ssh()
            elif action == 'node.runner.inspect':
                result = self._inspect_runner()
            elif action == 'node.runner.recover':
                result = self._recover_runner()
            elif action == 'node.runtime.converge':
                from agentos_node.client_runtime_converge import execute_client_runtime_converge
                result = execute_client_runtime_converge(task)
            elif action == 'threads.gui.read':
                from agentos_node.social.threads_gui_client import capability_ready as threads_gui_read_ready, read_threads_dm
                if not threads_gui_read_ready():
                    raise RuntimeError('threads_gui_read_capability_unavailable')
                result = read_threads_dm(account=str(task.get('account') or 'mio.milkcat'))
            elif action == 'agent.session.discover':
                result = {'session_index': self._session_bridge(task).discover()}
            elif action in {'agent.session.attach', 'agent.session.inspect', 'agent.context.harvest', 'agent.context.inject', 'agent.session.handoff'}:
                op = {
                    'agent.session.attach': 'attach',
                    'agent.session.inspect': 'snapshot',
                    'agent.context.harvest': 'harvest',
                    'agent.context.inject': 'inject',
                    'agent.session.handoff': 'handoff',
                }[str(action)]
                request = self._session_bridge(task).request(
                    op,
                    session_id=str(task.get('session_id') or '') or None,
                    payload=dict(task.get('payload') or {}),
                )
                result = {'session_request': request}
            elif action == 'agent.session.receipt':
                request_id = str(task.get('request_id') or '')
                if not request_id:
                    raise ValueError('request_id is required')
                result = {'session_receipt': self._session_bridge(task).receipt(request_id)}
            elif action == 'desktop.session.inspect':
                result = {'desktop': interactive_desktop.session_info()}
            elif action == 'desktop.windows.inspect':
                result = interactive_desktop.inspect_windows()
            elif action == 'desktop.open_url':
                url = str(task.get('url') or '')
                if platform.system() == 'Darwin':
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.scheme not in {'http','https'} or not parsed.netloc:
                        raise ValueError('desktop.open_url requires an http(s) URL')
                    p = subprocess.run(['open', url], capture_output=True, text=True, timeout=15, check=False)
                    if p.returncode != 0:
                        raise RuntimeError((p.stderr or p.stdout or 'open failed')[-1000:])
                    result = {'opened': True, 'url': url}
                else:
                    result = interactive_desktop.open_url(url)
            elif action == 'desktop.screenshot':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else Path.cwd()
                result = interactive_desktop.screenshot(workspace, quality=int(task.get('quality') or 55))
            elif action == 'desktop.windows.tile':
                result = interactive_desktop.tile_windows(task)
            elif action == 'desktop.demo.start':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.start(
                    workspace,
                    label=str(task.get('label') or 'AgentOS Demo'),
                    stage=str(task.get('stage') or 'Starting'),
                    max_seconds=int(task.get('max_seconds') or 900),
                )
            elif action == 'desktop.demo.stage':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.set_stage(workspace, str(task.get('stage') or ''))
            elif action == 'desktop.demo.stop':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.stop(workspace, final_stage=str(task.get('final_stage') or 'Verified'))
            elif action == 'desktop.mouse':
                result = interactive_desktop.mouse(task)
            elif action == 'desktop.keyboard':
                result = interactive_desktop.keyboard(task)
            else:
                adapter = self.adapters.resolve(str(action or ''))
                if adapter is None:
                    raise ValueError(f'unsupported action: {action}')
                result = adapter.execute(task)
                if not isinstance(result, dict):
                    raise TypeError(f'adapter result must be object: {adapter.adapter_id}')
                result = dict(result)
                result.setdefault('adapter_id', str(adapter.adapter_id))
            receipt.update(result)
            receipt['ok'] = True
        except Exception as exc:
            receipt['error'] = f'{type(exc).__name__}: {exc}'
        receipt['completed_at'] = _utc_now()
        return receipt

    def _inspect_ssh(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.ssh.inspect is Linux-only')
        status = subprocess.run(
            ['systemctl', 'is-active', 'ssh'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        listeners = subprocess.run(
            ['ss', '-lnt'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        port22 = any(
            line.split()[3].endswith(':22')
            for line in listeners.stdout.splitlines()
            if len(line.split()) >= 4
        )
        return {
            'ssh_service_active': status.returncode == 0 and status.stdout.strip() == 'active',
            'ssh_service_state': status.stdout.strip()[:64] or 'unknown',
            'port22_listening': port22,
        }

    def _recover_ssh(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.ssh.recover is Linux-only')
        before = self._inspect_ssh()
        restart_argv = ['systemctl', 'restart', 'ssh']
        if hasattr(os, 'geteuid') and os.geteuid() != 0:
            restart_argv = ['sudo', '-n', *restart_argv]
        restart = subprocess.run(
            restart_argv,
            capture_output=True, text=True, timeout=20, check=False,
        )
        after = self._inspect_ssh()
        return {
            'restart_returncode': restart.returncode,
            'ssh_service_active_before': before['ssh_service_active'],
            'port22_listening_before': before['port22_listening'],
            'ssh_service_active': after['ssh_service_active'],
            'ssh_service_state': after['ssh_service_state'],
            'port22_listening': after['port22_listening'],
            'recovered': restart.returncode == 0 and after['ssh_service_active'] and after['port22_listening'],
        }

    def _runner_units(self) -> list[str]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.runner.inspect is Linux-only')
        listing = subprocess.run(
            ['systemctl', 'list-units', '--type=service', '--all', '--no-legend', '--no-pager', 'actions.runner.*.service'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        units: list[str] = []
        for line in listing.stdout.splitlines():
            fields = line.split()
            if not fields:
                continue
            unit = fields[0].strip()
            if (
                unit.startswith('actions.runner.')
                and unit.endswith('.service')
                and all(ch.isalnum() or ch in '._@-' for ch in unit)
            ):
                units.append(unit)
        return sorted(set(units))

    def _inspect_runner(self) -> dict[str, Any]:
        units = self._runner_units()
        active = 0
        failed = 0
        for unit in units:
            status = subprocess.run(
                ['systemctl', 'is-active', unit],
                capture_output=True, text=True, timeout=10, check=False,
            )
            state = status.stdout.strip()
            if status.returncode == 0 and state == 'active':
                active += 1
            elif state == 'failed':
                failed += 1
        return {
            'runner_unit_count': len(units),
            'runner_active_count': active,
            'runner_failed_count': failed,
            'runner_healthy': bool(units) and active == len(units),
        }

    def _recover_runner(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.runner.recover is Linux-only')
        before = self._inspect_runner()
        units = self._runner_units()
        restart_returncodes: list[int] = []
        for unit in units:
            argv = ['systemctl', 'restart', unit]
            if hasattr(os, 'geteuid') and os.geteuid() != 0:
                argv = ['sudo', '-n', *argv]
            restart = subprocess.run(
                argv, capture_output=True, text=True, timeout=30, check=False,
            )
            restart_returncodes.append(restart.returncode)
        after = self._inspect_runner()
        return {
            'runner_unit_count': after['runner_unit_count'],
            'runner_active_count_before': before['runner_active_count'],
            'runner_active_count': after['runner_active_count'],
            'runner_failed_count': after['runner_failed_count'],
            'restart_attempted_count': len(units),
            'restart_failed_count': sum(1 for code in restart_returncodes if code != 0),
            'runner_healthy': after['runner_healthy'],
            'recovered': bool(units) and all(code == 0 for code in restart_returncodes) and after['runner_healthy'],
        }

    def _inspect_processes(self, task: dict[str, Any]) -> dict[str, Any]:
        query = str(task.get('query') or '').strip().lower()
        limit = max(1, min(int(task.get('limit') or 50), 200))
        if platform.system() == 'Windows':
            argv = ['powershell.exe','-NoProfile','-NonInteractive','-Command','Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress']
        else:
            argv = ['ps','-axo','pid=,ppid=,comm=,args=']
        p = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or 'process inspection failed')[-1000:])
        lines = [line for line in p.stdout.splitlines() if line.strip()]
        if query:
            lines = [line for line in lines if query in line.lower()]
        return {'processes': lines[:limit], 'count': min(len(lines), limit), 'truncated': len(lines) > limit}

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
        if platform.system() == 'Windows':
            creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
            proc = subprocess.Popen(
                [resolved, *argv],
                cwd=str(cwd),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = int(proc.returncode or 0)
            except subprocess.TimeoutExpired:
                # Kill the complete Windows process tree. Some GUI/UIA providers
                # can leave descendants alive after the direct child is killed,
                # which otherwise wedges the persistent Thin Client daemon.
                subprocess.run(
                    ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except Exception:
                    stdout, stderr = '', ''
                raise TimeoutError(f'shell.exec timed out after {timeout}s and process tree was terminated')
        else:
            completed = subprocess.run([resolved, *argv], cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
            returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        return {
            'returncode': returncode,
            'stdout': stdout[-30000:],
            'stderr': stderr[-10000:],
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
, text, re.IGNORECASE)
        return match.group(1) if match else ''

    def _project_matches(self, project_id: str) -> list[Path]:
        target = project_id.casefold()
        matches: list[Path] = []
        seen: set[str] = set()
        visited = 0
        skip = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.next', 'dist', 'build'}

        for configured in self.policy.readable_roots:
            base = configured.expanduser().resolve()
            if not base.is_dir():
                continue
            direct = base if base.name.casefold() == target else base / project_id
            if direct.is_dir() and self.policy.can_read(direct):
                key = str(direct.resolve()).casefold()
                if key not in seen:
                    seen.add(key)
                    matches.append(direct.resolve())
            for current, dirs, _files in os.walk(base):
                current_path = Path(current)
                try:
                    depth = len(current_path.relative_to(base).parts)
                except ValueError:
                    continue
                dirs[:] = [name for name in dirs if name not in skip]
                if depth >= 4:
                    dirs[:] = []
                visited += 1
                if visited > 800:
                    break
                if current_path.name.casefold() != target:
                    continue
                if not self.policy.can_read(current_path):
                    continue
                key = str(current_path.resolve()).casefold()
                if key not in seen:
                    seen.add(key)
                    matches.append(current_path.resolve())
                dirs[:] = []
                if len(matches) >= 5:
                    return matches
        return matches

    def _inspect_project(self, task: dict[str, Any]) -> dict[str, Any]:
        project_id = str(task.get('project_id') or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', project_id):
            raise ValueError('invalid project_id')
        matches = self._project_matches(project_id)
        if not matches:
            return {
                'project_inspection': {
                    'schema': 'agentos.project-inspection/v1',
                    'project_id': project_id,
                    'state': 'NOT_FOUND',
                    'match_count': 0,
                }
            }
        if len(matches) != 1:
            return {
                'project_inspection': {
                    'schema': 'agentos.project-inspection/v1',
                    'project_id': project_id,
                    'state': 'AMBIGUOUS',
                    'match_count': len(matches),
                }
            }

        root = matches[0]
        result: dict[str, Any] = {
            'schema': 'agentos.project-inspection/v1',
            'project_id': project_id,
            'state': 'FOUND',
            'match_count': 1,
            'git_repository': False,
            'git_head': '',
            'git_branch': '',
            'worktree_clean': None,
            'dirty_count': 0,
            'untracked_count': 0,
            'remote_identity': '',
            'last_commit_at': '',
        }
        if shutil.which('git') is None:
            return {'project_inspection': result}

        def git(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ['git', '-C', str(root), *args],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )

        inside = git('rev-parse', '--is-inside-work-tree')
        if inside.returncode != 0 or (inside.stdout or '').strip().lower() != 'true':
            return {'project_inspection': result}

        result['git_repository'] = True
        head = git('rev-parse', 'HEAD')
        if head.returncode == 0:
            value = (head.stdout or '').strip().lower()
            if re.fullmatch(r'[0-9a-f]{40}', value):
                result['git_head'] = value

        branch = git('branch', '--show-current')
        if branch.returncode == 0:
            result['git_branch'] = (branch.stdout or '').strip()[:128]

        status = git('status', '--porcelain=v1', '-uall')
        if status.returncode == 0:
            rows = [line for line in (status.stdout or '').splitlines() if line.strip()]
            result['dirty_count'] = len(rows)
            result['untracked_count'] = sum(1 for line in rows if line.startswith('??'))
            result['worktree_clean'] = not rows

        remote = git('config', '--get', 'remote.origin.url')
        if remote.returncode == 0:
            result['remote_identity'] = self._safe_git_remote_identity(remote.stdout or '')

        committed = git('show', '-s', '--format=%cI', 'HEAD')
        if committed.returncode == 0:
            result['last_commit_at'] = (committed.stdout or '').strip()[:64]

        return {'project_inspection': result}

    def capability_manifest(self) -> dict[str, Any]:
        tools = self.discover_tools()
        surface_inventory = self.surface_inventory()
        caps = [
            'context.harvest', 'process.inspect', 'tool.presence', 'agent.surface.inspect',
            'agent.executor.discover', 'agent.executor.reconcile',
        ]
        if platform.system() == 'Linux':
            caps.extend(['node.ssh.inspect', 'node.ssh.recover', 'node.runner.inspect', 'node.runner.recover'])
        caps.extend(surface_inventory.get('capabilities') or [])

        # Session bridge capabilities are provider-authorized and must be
        # advertised only when a configured bridge is actually ready.
        # This keeps Node discovery aligned with what execute() can really do.
        for provider in ('antigravity', 'gemini', 'claude-code', 'codex', 'cursor', 'vscode'):
            try:
                from agentos_node.session_bridge import describe_bridge
                descriptor = describe_bridge(provider)
            except Exception:
                descriptor = None
            if descriptor and descriptor.get('ready'):
                caps.extend(descriptor.get('capabilities') or [])
                # Receipts are part of the same governed bridge surface.
                caps.append('agent.session.receipt')
        if self.policy.allowed_executables:
            caps.append('shell.exec')
        if self.policy.readable_roots:
            caps.append('filesystem.read')
        if self.policy.writable_roots:
            caps.append('filesystem.write')
        if self.policy.employee_wake_root is not None:
            caps.append('agent.employee.wake.deliver')
        if platform.system() == 'Windows':
            caps.extend([
                'desktop.session.inspect', 'desktop.windows.inspect', 'desktop.screenshot',
                'desktop.open_url', 'desktop.mouse', 'desktop.keyboard',
                'desktop.windows.tile', 'desktop.demo.start', 'desktop.demo.stage', 'desktop.demo.stop',
            ])
        elif platform.system() == 'Darwin':
            caps.extend(['desktop.open_url', 'node.runtime.converge'])
            try:
                from agentos_node.social.threads_gui_client import capability_ready as threads_gui_read_ready
                if threads_gui_read_ready():
                    caps.append('threads.gui.read')
            except Exception:
                pass
        elif platform.system() == 'Linux':
            caps.extend(_linux_gui_worker_capabilities())
        caps.extend(self.adapters.capabilities())
        from agentos_node.executor_reconcile import discover_executor_inventory
        executor_inventory = discover_executor_inventory(probe_health=False)
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
            'capabilities': sorted(set(caps)),
            'tool_presence': tools,
            'surface_inventory': surface_inventory,
            'executor_inventory': executor_inventory,
            'adapters': self.adapters.describe(),
            'runtime': observe_runtime(),
            'workspace_roots': {
                'readable': [str(p.expanduser().resolve()) for p in self.policy.readable_roots],
                'writable': [str(p.expanduser().resolve()) for p in self.policy.writable_roots],
            },
        }

    def heartbeat(self) -> dict[str, Any]:
        manifest = self.capability_manifest()
        return {
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': self.identity.realm_id,
            'node_id': self.identity.node_id,
            'role': self.identity.role,
            'status': 'online',
            'observed_at': _utc_now(),
            'uptime_seconds': max(0, int(time.time() - datetime.fromisoformat(self.started_at.replace('Z', '+00:00')).timestamp())),
            'capability_count': len(manifest['capabilities']),
            'surface_count': int((manifest.get('surface_inventory') or {}).get('surface_count') or 0),
            'manifest': manifest,
        }

    def _session_bridge(self, task: dict[str, Any]) -> FileSessionBridge:
        provider = str(task.get('provider') or '').strip()
        if not provider:
            raise ValueError('provider is required for session bridge action')
        return FileSessionBridge.from_environment(provider)

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
            elif action == 'agent.employee.wake.deliver':
                if self.policy.employee_wake_root is None:
                    raise PermissionError('employee_wake_inbox_not_configured')
                from agentos_node.employee_wake_inbox import deliver_employee_wake
                result = deliver_employee_wake(
                    task,
                    self.policy.employee_wake_root,
                    expected_node_id=self.identity.node_id,
                )
            elif action == 'agent.surface.inspect':
                result = {'surface_inventory': self.surface_inventory()}
            elif action == 'agent.executor.discover':
                from agentos_node.executor_reconcile import discover_executor_inventory
                result = {'executor_inventory': discover_executor_inventory(probe_health=False)}
            elif action == 'agent.executor.reconcile':
                from agentos_node.executor_reconcile import reconcile_executor_adoption
                result = reconcile_executor_adoption(node_id=self.identity.node_id)
            elif action == 'process.inspect':
                result = self._inspect_processes(task)
            elif action == 'node.ssh.inspect':
                result = self._inspect_ssh()
            elif action == 'node.ssh.recover':
                result = self._recover_ssh()
            elif action == 'node.runner.inspect':
                result = self._inspect_runner()
            elif action == 'node.runner.recover':
                result = self._recover_runner()
            elif action == 'node.runtime.converge':
                from agentos_node.client_runtime_converge import execute_client_runtime_converge
                result = execute_client_runtime_converge(task)
            elif action == 'threads.gui.read':
                from agentos_node.social.threads_gui_client import capability_ready as threads_gui_read_ready, read_threads_dm
                if not threads_gui_read_ready():
                    raise RuntimeError('threads_gui_read_capability_unavailable')
                result = read_threads_dm(account=str(task.get('account') or 'mio.milkcat'))
            elif action == 'agent.session.discover':
                result = {'session_index': self._session_bridge(task).discover()}
            elif action in {'agent.session.attach', 'agent.session.inspect', 'agent.context.harvest', 'agent.context.inject', 'agent.session.handoff'}:
                op = {
                    'agent.session.attach': 'attach',
                    'agent.session.inspect': 'snapshot',
                    'agent.context.harvest': 'harvest',
                    'agent.context.inject': 'inject',
                    'agent.session.handoff': 'handoff',
                }[str(action)]
                request = self._session_bridge(task).request(
                    op,
                    session_id=str(task.get('session_id') or '') or None,
                    payload=dict(task.get('payload') or {}),
                )
                result = {'session_request': request}
            elif action == 'agent.session.receipt':
                request_id = str(task.get('request_id') or '')
                if not request_id:
                    raise ValueError('request_id is required')
                result = {'session_receipt': self._session_bridge(task).receipt(request_id)}
            elif action == 'desktop.session.inspect':
                result = {'desktop': interactive_desktop.session_info()}
            elif action == 'desktop.windows.inspect':
                result = interactive_desktop.inspect_windows()
            elif action == 'desktop.open_url':
                url = str(task.get('url') or '')
                if platform.system() == 'Darwin':
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.scheme not in {'http','https'} or not parsed.netloc:
                        raise ValueError('desktop.open_url requires an http(s) URL')
                    p = subprocess.run(['open', url], capture_output=True, text=True, timeout=15, check=False)
                    if p.returncode != 0:
                        raise RuntimeError((p.stderr or p.stdout or 'open failed')[-1000:])
                    result = {'opened': True, 'url': url}
                else:
                    result = interactive_desktop.open_url(url)
            elif action == 'desktop.screenshot':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else Path.cwd()
                result = interactive_desktop.screenshot(workspace, quality=int(task.get('quality') or 55))
            elif action == 'desktop.windows.tile':
                result = interactive_desktop.tile_windows(task)
            elif action == 'desktop.demo.start':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.start(
                    workspace,
                    label=str(task.get('label') or 'AgentOS Demo'),
                    stage=str(task.get('stage') or 'Starting'),
                    max_seconds=int(task.get('max_seconds') or 900),
                )
            elif action == 'desktop.demo.stage':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.set_stage(workspace, str(task.get('stage') or ''))
            elif action == 'desktop.demo.stop':
                workspace = self.policy.writable_roots[0] if self.policy.writable_roots else desktop_demo.default_workspace()
                result = desktop_demo.stop(workspace, final_stage=str(task.get('final_stage') or 'Verified'))
            elif action == 'desktop.mouse':
                result = interactive_desktop.mouse(task)
            elif action == 'desktop.keyboard':
                result = interactive_desktop.keyboard(task)
            else:
                adapter = self.adapters.resolve(str(action or ''))
                if adapter is None:
                    raise ValueError(f'unsupported action: {action}')
                result = adapter.execute(task)
                if not isinstance(result, dict):
                    raise TypeError(f'adapter result must be object: {adapter.adapter_id}')
                result = dict(result)
                result.setdefault('adapter_id', str(adapter.adapter_id))
            receipt.update(result)
            receipt['ok'] = True
        except Exception as exc:
            receipt['error'] = f'{type(exc).__name__}: {exc}'
        receipt['completed_at'] = _utc_now()
        return receipt

    def _inspect_ssh(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.ssh.inspect is Linux-only')
        status = subprocess.run(
            ['systemctl', 'is-active', 'ssh'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        listeners = subprocess.run(
            ['ss', '-lnt'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        port22 = any(
            line.split()[3].endswith(':22')
            for line in listeners.stdout.splitlines()
            if len(line.split()) >= 4
        )
        return {
            'ssh_service_active': status.returncode == 0 and status.stdout.strip() == 'active',
            'ssh_service_state': status.stdout.strip()[:64] or 'unknown',
            'port22_listening': port22,
        }

    def _recover_ssh(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.ssh.recover is Linux-only')
        before = self._inspect_ssh()
        restart_argv = ['systemctl', 'restart', 'ssh']
        if hasattr(os, 'geteuid') and os.geteuid() != 0:
            restart_argv = ['sudo', '-n', *restart_argv]
        restart = subprocess.run(
            restart_argv,
            capture_output=True, text=True, timeout=20, check=False,
        )
        after = self._inspect_ssh()
        return {
            'restart_returncode': restart.returncode,
            'ssh_service_active_before': before['ssh_service_active'],
            'port22_listening_before': before['port22_listening'],
            'ssh_service_active': after['ssh_service_active'],
            'ssh_service_state': after['ssh_service_state'],
            'port22_listening': after['port22_listening'],
            'recovered': restart.returncode == 0 and after['ssh_service_active'] and after['port22_listening'],
        }

    def _runner_units(self) -> list[str]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.runner.inspect is Linux-only')
        listing = subprocess.run(
            ['systemctl', 'list-units', '--type=service', '--all', '--no-legend', '--no-pager', 'actions.runner.*.service'],
            capture_output=True, text=True, timeout=10, check=False,
        )
        units: list[str] = []
        for line in listing.stdout.splitlines():
            fields = line.split()
            if not fields:
                continue
            unit = fields[0].strip()
            if (
                unit.startswith('actions.runner.')
                and unit.endswith('.service')
                and all(ch.isalnum() or ch in '._@-' for ch in unit)
            ):
                units.append(unit)
        return sorted(set(units))

    def _inspect_runner(self) -> dict[str, Any]:
        units = self._runner_units()
        active = 0
        failed = 0
        for unit in units:
            status = subprocess.run(
                ['systemctl', 'is-active', unit],
                capture_output=True, text=True, timeout=10, check=False,
            )
            state = status.stdout.strip()
            if status.returncode == 0 and state == 'active':
                active += 1
            elif state == 'failed':
                failed += 1
        return {
            'runner_unit_count': len(units),
            'runner_active_count': active,
            'runner_failed_count': failed,
            'runner_healthy': bool(units) and active == len(units),
        }

    def _recover_runner(self) -> dict[str, Any]:
        if platform.system() != 'Linux':
            raise RuntimeError('node.runner.recover is Linux-only')
        before = self._inspect_runner()
        units = self._runner_units()
        restart_returncodes: list[int] = []
        for unit in units:
            argv = ['systemctl', 'restart', unit]
            if hasattr(os, 'geteuid') and os.geteuid() != 0:
                argv = ['sudo', '-n', *argv]
            restart = subprocess.run(
                argv, capture_output=True, text=True, timeout=30, check=False,
            )
            restart_returncodes.append(restart.returncode)
        after = self._inspect_runner()
        return {
            'runner_unit_count': after['runner_unit_count'],
            'runner_active_count_before': before['runner_active_count'],
            'runner_active_count': after['runner_active_count'],
            'runner_failed_count': after['runner_failed_count'],
            'restart_attempted_count': len(units),
            'restart_failed_count': sum(1 for code in restart_returncodes if code != 0),
            'runner_healthy': after['runner_healthy'],
            'recovered': bool(units) and all(code == 0 for code in restart_returncodes) and after['runner_healthy'],
        }

    def _inspect_processes(self, task: dict[str, Any]) -> dict[str, Any]:
        query = str(task.get('query') or '').strip().lower()
        limit = max(1, min(int(task.get('limit') or 50), 200))
        if platform.system() == 'Windows':
            argv = ['powershell.exe','-NoProfile','-NonInteractive','-Command','Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress']
        else:
            argv = ['ps','-axo','pid=,ppid=,comm=,args=']
        p = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or 'process inspection failed')[-1000:])
        lines = [line for line in p.stdout.splitlines() if line.strip()]
        if query:
            lines = [line for line in lines if query in line.lower()]
        return {'processes': lines[:limit], 'count': min(len(lines), limit), 'truncated': len(lines) > limit}

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
        if platform.system() == 'Windows':
            creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
            proc = subprocess.Popen(
                [resolved, *argv],
                cwd=str(cwd),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                returncode = int(proc.returncode or 0)
            except subprocess.TimeoutExpired:
                # Kill the complete Windows process tree. Some GUI/UIA providers
                # can leave descendants alive after the direct child is killed,
                # which otherwise wedges the persistent Thin Client daemon.
                subprocess.run(
                    ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except Exception:
                    stdout, stderr = '', ''
                raise TimeoutError(f'shell.exec timed out after {timeout}s and process tree was terminated')
        else:
            completed = subprocess.run([resolved, *argv], cwd=str(cwd), text=True, capture_output=True, timeout=timeout, check=False)
            returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        return {
            'returncode': returncode,
            'stdout': stdout[-30000:],
            'stderr': stderr[-10000:],
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
