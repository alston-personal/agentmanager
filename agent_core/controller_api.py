from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

from agent_core.realm_fabric import RealmFabricStore
from agent_core.runtime_ota import ALLOWED_SOURCE_REFS, RuntimeOTAPolicyStore


CONTROLLER_ACTION_CAPABILITY = {
    'agent.surface.inspect': 'agent.surface.inspect',
    'agent.session.discover': 'agent.session.discover',
    'agent.session.inspect': 'agent.session.inspect',
    'agent.context.harvest': 'agent.context.harvest',
    'desktop.session.inspect': 'desktop.session.inspect',
    'desktop.windows.inspect': 'desktop.windows.inspect',
    'desktop.screenshot': 'desktop.screenshot',
    'desktop.open_url': 'desktop.open_url',
    'desktop.window.stage': 'desktop.windows.tile',
    'desktop.pointer.click': 'desktop.mouse',
    'desktop.text.insert': 'desktop.keyboard',
    'node.runtime.converge': 'shell.exec',
    'node.ssh.inspect': 'node.ssh.inspect',
    'node.ssh.recover': 'node.ssh.recover',
    'node.runner.inspect': 'node.runner.inspect',
    'node.runner.recover': 'node.runner.recover',
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

    def scheduler(self) -> dict[str, Any]:
        """Read-only structured projection of the AgentOS role scheduler.

        The scheduler owns execution state outside the Realm Fabric registry, so
        the controller projects only bounded operational metadata: worker role,
        state, current typed action, priority, declared locks, queue depth and
        recent failure classifications. File paths and raw worker output are
        deliberately excluded.
        """
        data_root = Path(os.environ.get('AGENTOS_DATA_ROOT') or os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        status_path = data_root / 'runtime' / 'bootstrap-scheduler' / 'status.json'
        incident_root = data_root / 'runtime' / 'bootstrap-scheduler' / 'incidents'

        try:
            raw = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            raw = {}
        workers_raw = raw.get('workers') if isinstance(raw.get('workers'), dict) else {}
        workers: dict[str, Any] = {}
        lock_holders: dict[str, str] = {}
        for worker_id, row in sorted(workers_raw.items()):
            if not isinstance(row, dict):
                continue
            current_raw = row.get('current_job') if isinstance(row.get('current_job'), dict) else None
            current = None
            if current_raw is not None:
                locks = [str(item)[:128] for item in (current_raw.get('locks') or []) if isinstance(item, str)]
                current = {
                    'request_id': str(current_raw.get('request_id') or '')[:160] or None,
                    'action': str(current_raw.get('action') or '')[:160] or None,
                    'priority': str(current_raw.get('priority') or '')[:32] or None,
                    'locks': locks,
                }
                for lock_key in locks:
                    lock_holders.setdefault(lock_key, str(worker_id)[:128])
            workers[str(worker_id)[:128]] = {
                'role': str(row.get('role') or '')[:32] or None,
                'state': str(row.get('state') or 'unknown')[:32],
                'heartbeat': str(row.get('heartbeat') or '')[:64] or None,
                'current_job': current,
            }

        queue_raw = raw.get('queue_depth') if isinstance(raw.get('queue_depth'), dict) else {}
        queue_depth = {
            role: max(0, int(queue_raw.get(role) or 0))
            for role in ('control', 'social', 'gui', 'build')
        }

        incidents: list[dict[str, Any]] = []
        if incident_root.exists():
            try:
                paths = sorted(incident_root.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
            except OSError:
                paths = []
            for path in paths[:20]:
                try:
                    row = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(row, dict):
                    continue
                incidents.append({
                    'project': str(row.get('project') or '')[:80] or None,
                    'request_id': str(row.get('request_id') or '')[:160] or None,
                    'action': str(row.get('action') or '')[:160] or None,
                    'priority': str(row.get('priority') or '')[:32] or None,
                    'requested_capabilities': [
                        str(item)[:128] for item in (row.get('requested_capabilities') or [])
                        if isinstance(item, str)
                    ][:32],
                    'preferred_node': str(row.get('preferred_node') or '')[:128] or None,
                    'failure_class': str(row.get('failure_class') or '')[:64] or None,
                    'fallback_attempted': bool(row.get('fallback_attempted')),
                    'receipt_required': bool(row.get('receipt_required')),
                    'observed_at': str(row.get('observed_at') or '')[:64] or None,
                })

        relevant_caps = {
            'threads.gui.read', 'threads.gui.write', 'threads.api.read',
            'browser.gui', 'browser.cdp', 'desktop.open_url', 'node.runtime.converge',
        }
        failover_candidates = []
        for node in self.nodes().get('nodes') or []:
            if not isinstance(node, dict) or node.get('role') != 'client':
                continue
            caps = sorted(relevant_caps.intersection(set(node.get('capabilities') or [])))
            if caps or node.get('node_id') in {'mbpr', 'vopc5750', 'oracle-exec'}:
                failover_candidates.append({
                    'node_id': str(node.get('node_id') or '')[:128],
                    'status': str(node.get('status') or 'unknown')[:32],
                    'platform': str(node.get('platform') or '')[:64] or None,
                    'capabilities': caps,
                })

        return {
            'schema': 'agentos.runner-pool/v1',
            'node': str(raw.get('node') or 'oracle')[:128],
            'updated_at': str(raw.get('updated_at') or '')[:64] or None,
            'worker_count': len(workers),
            'busy_worker_count': sum(1 for row in workers.values() if row.get('state') == 'running'),
            'queue_depth': queue_depth,
            'workers': workers,
            'lock_holders': lock_holders,
            'recent_incidents': incidents,
            'failover_candidates': failover_candidates,
        }

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
        source_ref: str = 'core/integration',
        *,
        cwd: str,
        platform_name: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
            raise ValueError('source_commit must be a 40-character lowercase git SHA')
        if source_ref not in ALLOWED_SOURCE_REFS:
            raise ValueError('source_ref is not allowlisted')
        if not str(cwd or '').strip():
            raise ValueError('runtime convergence cwd is required')

        platform_name = str(platform_name or '').strip()
        if platform_name == 'Windows':
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
foreach($proc in $old){ Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }
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

        if platform_name == 'Linux':
            script = r'''from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

source_commit='SOURCE_COMMIT'
source_ref='SOURCE_REF'
cwd=Path.cwd()
candidates=[cwd/'AgentOS', cwd]
repo=next((p for p in candidates if (p/'.git').exists()), None)
if repo is None:
    raise SystemExit('agentos_repo_missing')
subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin',source_commit],check=True,timeout=45)
subprocess.run(['git','-C',str(repo),'checkout','--detach',source_commit],check=True,timeout=30)

runtime=Path.home()/'.local/share/agentos'
runtime.mkdir(parents=True,exist_ok=True)
prov={
  'schema':'agentos.thin-client-runtime/v0.1',
  'source_ref':source_ref,
  'source_commit':source_commit,
  'installed_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
  'install_mode':'controller-single-owner-converge',
}
(runtime/'runtime-provenance.json').write_text(json.dumps(prov,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

helper=runtime/'agentos-runtime-converge-linux.py'
status=runtime/'runtime-convergence.json'
helper.write_text("""import json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
time.sleep(10)
unit='agentos-thin-client.service'
subprocess.run(['systemctl','--user','restart',unit],check=True,timeout=20)
state='unknown'
for _ in range(12):
    time.sleep(1)
    p=subprocess.run(['systemctl','--user','is-active',unit],capture_output=True,text=True,timeout=5)
    state=p.stdout.strip()
    if p.returncode==0 and state=='active':
        break
result={
  'schema':'agentos.node-runtime-convergence/v0.1',
  'source_commit':'SOURCE_COMMIT',
  'source_ref':'SOURCE_REF',
  'thin_client_service_state':state,
  'converged':state=='active',
  'completed_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
}
Path('STATUS_PATH').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
raise SystemExit(0 if result['converged'] else 4)
""".replace('SOURCE_COMMIT',source_commit).replace('SOURCE_REF',source_ref).replace('STATUS_PATH',str(status)),encoding='utf-8')
subprocess.Popen([sys.executable,str(helper)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)
print('agentos_runtime_converge=PASS')
print('agentos_single_owner_convergence=DEFERRED')
print('agentos_source_commit='+source_commit)
'''.replace('SOURCE_COMMIT', source_commit).replace('SOURCE_REF', source_ref)
            return {
                'schema': 'agentos.node-task/v0.1',
                'task_id': task_id,
                'action': 'shell.exec',
                'controller_action': 'node.runtime.converge',
                'executable': 'python3',
                'argv': ['-c', script],
                'cwd': str(cwd),
                'timeout_seconds': 90,
                'cognition_ids_used': [],
            }

        raise ValueError(f'node runtime convergence unsupported on platform: {platform_name}')

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
            task = self._runtime_convergence_task(
                task_id, source_commit, source_ref, cwd=cwd,
                platform_name=str(node.get('platform') or ''),
            )
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

    @staticmethod
    def _typed_desktop_task(task_id: str, action: str, request: dict[str, Any]) -> dict[str, Any]:
        base = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'controller_action': action,
            'cognition_ids_used': list(request.get('cognition_ids_used') or []),
        }
        if action == 'desktop.window.stage':
            title = str(request.get('title_contains') or '').strip()
            zone = str(request.get('zone') or '').strip().lower()
            if not title or len(title) > 120:
                raise ValueError('desktop.window.stage requires title_contains 1..120 chars')
            if zone not in {'left', 'right', 'full'}:
                raise ValueError('desktop.window.stage zone must be left|right|full')
            reserve_top = int(request.get('reserve_top_px') if request.get('reserve_top_px') is not None else 8)
            margin = int(request.get('margin_px') if request.get('margin_px') is not None else 4)
            if not 0 <= reserve_top <= 160:
                raise ValueError('desktop.window.stage reserve_top_px must be 0..160')
            if not 0 <= margin <= 40:
                raise ValueError('desktop.window.stage margin_px must be 0..40')
            return {
                **base,
                'action': 'desktop.windows.tile',
                'windows': [{'title_contains': title, 'zone': zone}],
                'reserve_top_px': reserve_top,
                'margin_px': margin,
            }
        if action == 'desktop.pointer.click':
            if 'x' not in request or 'y' not in request:
                raise ValueError('desktop.pointer.click requires x and y')
            x, y = int(request['x']), int(request['y'])
            if not 0 <= x <= 16383 or not 0 <= y <= 16383:
                raise ValueError('desktop.pointer.click coordinates out of bounds')
            button = str(request.get('button') or 'left').strip().lower()
            if button not in {'left', 'right'}:
                raise ValueError('desktop.pointer.click button must be left|right')
            return {**base, 'action': 'desktop.mouse', 'operation': 'click', 'x': x, 'y': y, 'button': button}
        if action == 'desktop.text.insert':
            text = str(request.get('text') or '')
            if not text or len(text) > 1000:
                raise ValueError('desktop.text.insert text must contain 1..1000 characters')
            return {**base, 'action': 'desktop.keyboard', 'operation': 'type', 'text': text}
        raise ValueError(f'unsupported typed desktop action: {action}')

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
            typed_node_actions = {
                'desktop.window.stage': 'desktop.windows.tile',
                'desktop.pointer.click': 'desktop.mouse',
                'desktop.text.insert': 'desktop.keyboard',
            }
            compatible = (
                existing_action == action
                or (action == 'node.runtime.converge' and existing_action == 'shell.exec')
                or existing_action == typed_node_actions.get(action)
            )
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
                platform_name=str(node.get('platform') or ''),
            )
        elif action in {'desktop.window.stage', 'desktop.pointer.click', 'desktop.text.insert'}:
            task = self._typed_desktop_task(task_id, action, request)
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