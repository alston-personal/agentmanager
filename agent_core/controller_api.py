from __future__ import annotations

import re
import secrets
from typing import Any

from agent_core.realm_fabric import RealmFabricStore
from agent_core.runtime_ota import RuntimeOTAPolicyStore


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

    def __init__(self, fabric: RealmFabricStore, ota_policy: RuntimeOTAPolicyStore | None = None, executor_job_dispatcher: Any | None = None):
        self.fabric = fabric
        self.ota_policy = ota_policy or RuntimeOTAPolicyStore()
        self._executor_job_dispatcher = executor_job_dispatcher

    def _executor_dispatcher(self):
        if self._executor_job_dispatcher is None:
            from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
            self._executor_job_dispatcher = ActionRelayExecutorJobDispatcher()
        return self._executor_job_dispatcher

    def realm(self) -> dict[str, Any]:
        node_map = self.nodes()
        return {
            'schema': 'agentos.controller-realm/v0.1',
            'realm_id': node_map.get('realm_id'),
            'node_count': node_map.get('node_count', 0),
            'online_node_count': node_map.get('online_node_count', 0),
            'realm_capabilities': list(node_map.get('realm_capabilities') or []),
            'realm_tool_presence': list(node_map.get('realm_tool_presence') or []),
            'realm_surface_providers': list(node_map.get('realm_surface_providers') or []),
            'runtime_ota': self.ota_policy.load(),
            'runtime_converged_count': node_map.get('runtime_converged_count', 0),
            'runtime_drifted_count': node_map.get('runtime_drifted_count', 0),
            'runtime_unknown_count': node_map.get('runtime_unknown_count', 0),
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

    @staticmethod
    def _maintenance_cwd(node: dict[str, Any]) -> str:
        roots = node.get('workspace_roots') or {}
        readable = roots.get('readable') if isinstance(roots, dict) else None
        if not isinstance(readable, list):
            raise ValueError('node does not advertise readable workspace roots')
        candidates = [str(item).strip() for item in readable if str(item).strip()]
        if not candidates:
            raise ValueError('node does not advertise readable workspace roots')
        return candidates[0]

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
    def _runtime_convergence_task(
        task_id: str,
        source_commit: str,
        source_ref: str = 'feature/realm-node-fabric-readiness',
        *,
        cwd: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be a 40-character lowercase git SHA')
        if source_ref not in {'main', 'feature/realm-node-fabric-readiness'}:
            raise ValueError('source_ref is not allowlisted')
        if not str(cwd or '').strip():
            raise ValueError('runtime convergence cwd is required')
        script = r'''$ErrorActionPreference='Stop'
$install=Join-Path $env:LOCALAPPDATA 'AgentOS'
$base='https://raw.githubusercontent.com/alston-personal/agentmanager/SOURCE_COMMIT'
$files=@(
  'agentos_node/thin_client.py',
  'agentos_node/runtime_provenance.py',
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
$prov=@{
  schema='agentos.thin-client-runtime/v0.1'
  source_ref='SOURCE_REF'
  source_commit='SOURCE_COMMIT'
  installed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  install_mode='controller-single-owner-converge'
} | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $install 'runtime-provenance.json'),$prov,(New-Object System.Text.UTF8Encoding($false)))

$taskName='AgentOS Thin Client'
$watchdogName='AgentOS Thin Client Watchdog'
Get-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
Get-ScheduledTask -TaskName $watchdogName -ErrorAction Stop | Out-Null

# The task receipt must be submitted before the currently-serving daemon is
# retired. A detached, bounded convergence script runs after this task returns.
$convergeScript=Join-Path $install 'agentos-runtime-converge.ps1'
$statusPath=Join-Path $install 'runtime-convergence.json'
$body=@'
$ErrorActionPreference='Stop'
Start-Sleep -Seconds 10
$taskName='AgentOS Thin Client'
$watchdogName='AgentOS Thin Client Watchdog'
$statusPath='STATUS_PATH'
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$old=@(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^pythonw?\.exe$' -and
  $_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)'
})
foreach($proc in $old){
  Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName $taskName
$state='Unknown'
for($i=0;$i -lt 12;$i++){
  Start-Sleep -Seconds 1
  $state=[string](Get-ScheduledTask -TaskName $taskName -ErrorAction Stop).State
  if($state -eq 'Running'){ break }
}
$clients=@(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^pythonw?\.exe$' -and
  $_.CommandLine -match '(?i)-m\s+agentos_node\.client_cli\s+run(?:\s|$)'
})
$watchdog=Get-ScheduledTask -TaskName $watchdogName -ErrorAction Stop
$result=[ordered]@{
  schema='agentos.node-runtime-convergence/v0.1'
  source_commit='SOURCE_COMMIT'
  source_ref='SOURCE_REF'
  retired_client_count=$old.Count
  managed_client_count=$clients.Count
  thin_client_task_state=$state
  watchdog_present=($null -ne $watchdog)
  converged=($state -eq 'Running' -and $clients.Count -eq 1 -and $null -ne $watchdog)
  completed_at=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}
[System.IO.File]::WriteAllText($statusPath,($result | ConvertTo-Json),(New-Object System.Text.UTF8Encoding($false)))
if(-not $result.converged){ exit 4 }
'@
$body=$body.Replace('STATUS_PATH',$statusPath.Replace("'","''")).Replace('SOURCE_COMMIT','SOURCE_COMMIT').Replace('SOURCE_REF','SOURCE_REF')
[System.IO.File]::WriteAllText($convergeScript,$body,(New-Object System.Text.UTF8Encoding($false)))
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$convergeScript`""
Write-Output 'agentos_runtime_converge=PASS'
Write-Output 'agentos_single_owner_convergence=DEFERRED'
Write-Output 'agentos_watchdog_preserved=PASS'
Write-Output 'agentos_source_commit=SOURCE_COMMIT'
'''.replace('SOURCE_COMMIT', source_commit).replace('SOURCE_REF', source_ref)
        return {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'action': 'shell.exec',
            'controller_action': 'node.runtime.converge',
            'executable': 'powershell',
            'argv': ['-NoProfile', '-NonInteractive', '-Command', script],
            'cwd': str(cwd),
            'timeout_seconds': 60,
            'cognition_ids_used': [],
        }

    def rollout_runtime(self, request: dict[str, Any]) -> dict[str, Any]:
        source_commit = str(request.get('source_commit') or '').strip()
        source_ref = str(request.get('source_ref') or 'feature/realm-node-fabric-readiness').strip()
        auto_converge = bool(request.get('auto_converge', False))
        policy = self.ota_policy.set_desired(source_commit=source_commit, source_ref=source_ref, auto_converge=auto_converge)
        rollout_id = str(request.get('task_id') or '').strip() or 'ota_' + secrets.token_hex(8)
        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for node in self.nodes().get('nodes') or []:
            node_id = str(node.get('node_id') or '')
            if node.get('role') != 'client':
                skipped.append({'node_id': node_id, 'reason': 'not_client'})
                continue
            if node.get('status') != 'online':
                skipped.append({'node_id': node_id, 'reason': 'offline'})
                continue
            if node.get('runtime_status') == 'converged':
                skipped.append({'node_id': node_id, 'reason': 'already_converged'})
                continue
            if 'shell.exec' not in set(node.get('capabilities') or []):
                skipped.append({'node_id': node_id, 'reason': 'missing_maintenance_capability'})
                continue
            try:
                cwd = self._maintenance_cwd(node)
            except ValueError:
                skipped.append({'node_id': node_id, 'reason': 'missing_workspace_authority'})
                continue
            task_id = f'{rollout_id}_{node_id}'
            existing = self._existing_task(task_id)
            if existing is not None:
                results.append({'node_id': node_id, 'task_id': task_id, 'state': existing.get('state'), 'reused': True})
                continue
            task = self._runtime_convergence_task(task_id, source_commit, source_ref, cwd=cwd)
            queued = self.fabric.queue_task(node_id, task)
            results.append({'node_id': node_id, 'task_id': task_id, 'state': 'queued', 'queued_at': queued.get('queued_at'), 'reused': False, 'cwd': cwd})
        return {
            'schema': 'agentos.realm-runtime-rollout/v0.1',
            'ok': True,
            'action': 'realm.runtime.rollout',
            'rollout_id': rollout_id,
            'policy': policy,
            'queued_node_count': len(results),
            'skipped_node_count': len(skipped),
            'nodes': results,
            'skipped': skipped,
        }

    def verify_runtime_rollout(self, rollout_id: str) -> dict[str, Any]:
        rollout_id = str(rollout_id or '').strip()
        if not rollout_id:
            raise ValueError('rollout_id is required')
        policy = self.ota_policy.load()
        desired = str(policy.get('desired_source_commit') or '')
        nodes = [node for node in self.nodes().get('nodes') or [] if node.get('role') == 'client']
        observations: list[dict[str, Any]] = []
        for node in nodes:
            node_id = str(node.get('node_id') or '')
            task_id = f'{rollout_id}_{node_id}'
            receipt = self.fabric.get_receipt(task_id)
            observations.append({
                'node_id': node_id,
                'task_id': task_id,
                'task_receipt_ok': None if receipt is None else bool(receipt.get('ok')),
                'observed_runtime_commit': (node.get('runtime') or {}).get('source_commit'),
                'desired_runtime_commit': desired or None,
                'runtime_status': node.get('runtime_status'),
                'converged': node.get('runtime_status') == 'converged',
            })
        converged = [item for item in observations if item['converged']]
        pending = [item for item in observations if not item['converged']]
        return {
            'schema': 'agentos.realm-runtime-rollout-receipt/v0.1',
            'ok': not pending,
            'rollout_id': rollout_id,
            'desired_runtime_commit': desired or None,
            'client_node_count': len(observations),
            'converged_node_count': len(converged),
            'pending_node_count': len(pending),
            'nodes': observations,
        }

    def dispatch(self, node_id: str, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request.get('action') or '').strip()
        if action == 'realm.runtime.rollout':
            return self.rollout_runtime(request)

        node = self.node(node_id)
        if node.get('status') != 'online':
            raise ValueError(f'node is not online: {node_id}')
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
            task = self._runtime_convergence_task(
                task_id,
                str(request.get('source_commit') or '').strip(),
                str(request.get('source_ref') or 'feature/realm-node-fabric-readiness').strip(),
                cwd=self._maintenance_cwd(node),
            )
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
        if task_id.startswith('action-'):
            receipt = self._executor_dispatcher().inspect(task_id)
            if receipt is None:
                raise KeyError(task_id)
            return dict(receipt)
        receipt = self.fabric.get_receipt(task_id)
        if receipt is None:
            raise KeyError(task_id)
        return receipt