from __future__ import annotations

import re
import secrets
from typing import Any

from agent_core.realm_fabric import RealmFabricStore


CONTROLLER_ACTION_CAPABILITY = {
    'agent.surface.inspect': 'agent.surface.inspect',
    'agent.session.discover': 'agent.session.discover',
    'agent.session.inspect': 'agent.session.inspect',
    'agent.context.harvest': 'agent.context.harvest',
    'desktop.session.inspect': 'desktop.session.inspect',
    'desktop.windows.inspect': 'desktop.windows.inspect',
    'desktop.screenshot': 'desktop.screenshot',
    'desktop.open_url': 'desktop.open_url',
    'node.runtime.converge': 'shell.exec',
}


class ControllerService:
    """Governed controller-side facade for ONE."""

    def __init__(self, fabric: RealmFabricStore):
        self.fabric = fabric

    def realm(self) -> dict[str, Any]:
        node_map = self.fabric.node_registry.node_map()
        return {
            'schema': 'agentos.controller-realm/v0.1',
            'realm_id': node_map.get('realm_id'),
            'node_count': node_map.get('node_count', 0),
            'online_node_count': node_map.get('online_node_count', 0),
            'realm_capabilities': list(node_map.get('realm_capabilities') or []),
            'realm_tool_presence': list(node_map.get('realm_tool_presence') or []),
            'realm_surface_providers': list(node_map.get('realm_surface_providers') or []),
        }

    def nodes(self) -> dict[str, Any]:
        return self.fabric.node_registry.node_map()

    def node(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        node = next((item for item in self.nodes().get('nodes') or [] if item.get('node_id') == node_id), None)
        if node is None:
            raise KeyError(node_id)
        return node

    def _existing_task(self, task_id: str) -> dict[str, Any] | None:
        data = self.fabric.load()
        receipt = (data.get('receipts') or {}).get(task_id)
        if isinstance(receipt, dict):
            return {'state': 'completed', 'node_id': receipt.get('node_id'), 'action': receipt.get('action'), 'queued_at': None}
        for queued_node_id, queue in (data.get('tasks') or {}).items():
            for task in queue or []:
                if isinstance(task, dict) and task.get('task_id') == task_id:
                    return {
                        'state': 'queued',
                        'node_id': queued_node_id,
                        'action': task.get('controller_action') or task.get('action'),
                        'queued_at': task.get('queued_at'),
                    }
        return None

    @staticmethod
    def _runtime_convergence_task(task_id: str, source_commit: str) -> dict[str, Any]:
        if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be a 40-character lowercase git SHA')
        script = r'''$ErrorActionPreference='Stop'
$install=Join-Path $env:LOCALAPPDATA 'AgentOS'
$base='https://raw.githubusercontent.com/alston-personal/agentmanager/SOURCE_COMMIT'
$files=@(
  'agentos_node/thin_client.py',
  'agentos_node/interactive_desktop.py',
  'agentos_node/thin_client_transport.py',
  'agentos_node/client_cli.py',
  'agentos_node/agent_surfaces.py',
  'agentos_node/session_bridge.py',
  'agentos_node/onboarding.py'
)
foreach($rel in $files){
  $dest=Join-Path $install ($rel -replace '/','\\')
  $parent=Split-Path -Parent $dest
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} -Uri "$base/$rel" -OutFile $dest
}
$taskName='AgentOS Thin Client'
Get-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
Get-ScheduledTask -TaskName 'AgentOS Thin Client Watchdog' -ErrorAction Stop | Out-Null
$restart="Start-Sleep -Seconds 5; Stop-ScheduledTask -TaskName '$taskName' -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; Start-ScheduledTask -TaskName '$taskName'"
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-NonInteractive','-Command',$restart)
Write-Output 'agentos_runtime_converge=PASS'
Write-Output 'agentos_watchdog_preserved=PASS'
Write-Output 'agentos_source_commit=SOURCE_COMMIT'
'''.replace('SOURCE_COMMIT', source_commit)
        return {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'action': 'shell.exec',
            'controller_action': 'node.runtime.converge',
            'executable': 'powershell',
            'argv': ['-NoProfile', '-NonInteractive', '-Command', script],
            'timeout_seconds': 60,
            'cognition_ids_used': [],
        }

    def dispatch(self, node_id: str, request: dict[str, Any]) -> dict[str, Any]:
        node = self.node(node_id)
        if node.get('status') != 'online':
            raise ValueError(f'node is not online: {node_id}')
        action = str(request.get('action') or '').strip()
        required_capability = CONTROLLER_ACTION_CAPABILITY.get(action)
        if required_capability is None:
            raise PermissionError(f'controller action not permitted: {action}')
        if required_capability not in set(node.get('capabilities') or []):
            raise ValueError(f'node lacks capability: {required_capability}')

        task_id = str(request.get('task_id') or '').strip() or 'ctl_' + secrets.token_hex(12)
        existing = self._existing_task(task_id)
        if existing is not None:
            existing_action = str(existing.get('action') or '')
            compatible = existing_action == action or (action == 'node.runtime.converge' and existing_action == 'shell.exec')
            if existing.get('node_id') != node_id or not compatible:
                raise ValueError(f'task_id already belongs to another request: {task_id}')
            return {
                'schema': 'agentos.controller-dispatch/v0.1', 'ok': True, 'node_id': node_id,
                'task_id': task_id, 'action': action, 'queued_at': existing.get('queued_at'),
                'state': existing.get('state'), 'reused': True,
            }

        if action == 'node.runtime.converge':
            task = self._runtime_convergence_task(task_id, str(request.get('source_commit') or '').strip())
        else:
            task = {
                'schema': 'agentos.node-task/v0.1',
                'task_id': task_id,
                'action': action,
                'cognition_ids_used': list(request.get('cognition_ids_used') or []),
            }
            for key in ('provider', 'session_id', 'request_id', 'payload', 'url', 'quality'):
                if key in request:
                    task[key] = request[key]

        queued = self.fabric.queue_task(node_id, task)
        return {
            'schema': 'agentos.controller-dispatch/v0.1', 'ok': True, 'node_id': node_id,
            'task_id': task_id, 'action': action, 'queued_at': queued.get('queued_at'),
            'state': 'queued', 'reused': False,
        }

    def discover(self, node_id: str) -> dict[str, Any]:
        return self.dispatch(node_id, {'action': 'agent.surface.inspect'})

    def receipt(self, task_id: str) -> dict[str, Any]:
        task_id = str(task_id or '').strip()
        if not task_id:
            raise ValueError('task_id is required')
        receipt = self.fabric.get_receipt(task_id)
        if receipt is None:
            raise KeyError(task_id)
        return receipt
