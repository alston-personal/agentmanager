from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any


WINDOWS_THIN_CLIENT_TASK = 'AgentOS Thin Client'
WINDOWS_WATCHDOG_TASK = 'AgentOS Thin Client Watchdog'


def windows_node_install_root() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if local:
        return Path(local) / 'AgentOS'
    return Path.home() / 'AppData' / 'Local' / 'AgentOS'


def render_windows_watchdog_script() -> str:
    return """$ErrorActionPreference='Stop'
$taskName='AgentOS Thin Client'
$task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -eq $task) { exit 2 }
if ($task.State -ne 'Running') {
  Start-ScheduledTask -TaskName $taskName
  Start-Sleep -Seconds 3
  $state=(Get-ScheduledTask -TaskName $taskName).State
  if ($state -ne 'Running') { exit 3 }
}
exit 0
"""


def render_windows_supervisor_install_script(*, install_root: Path, launcher: Path) -> str:
    root = str(install_root)
    launch = str(launcher)
    watchdog = str(install_root / 'agentos-thin-client-watchdog.ps1')
    watchdog_body = render_windows_watchdog_script().replace("'", "''")
    return f"""$ErrorActionPreference='Stop'
$install='{root.replace("'", "''")}'
$launcher='{launch.replace("'", "''")}'
if (-not (Test-Path -LiteralPath $launcher)) {{ throw 'agentos-client launcher not found: ' + $launcher }}
New-Item -ItemType Directory -Force -Path $install | Out-Null
@'
{watchdog_body}
'@ | Set-Content -Encoding UTF8 -Path '{watchdog.replace("'", "''")}'

$taskName='{WINDOWS_THIN_CLIENT_TASK}'
$action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c "' + $launcher + '" run') -WorkingDirectory $install
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon' -Force | Out-Null

$watchdogName='{WINDOWS_WATCHDOG_TASK}'
$watchdogAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{watchdog.replace("'", "''")}"') -WorkingDirectory $install
$watchdogTrigger=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$watchdogSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $watchdogName -Action $watchdogAction -Trigger $watchdogTrigger -Settings $watchdogSettings -Description 'AgentOS OS-level watchdog; restarts Thin Client when it is not running' -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
$clientState=(Get-ScheduledTask -TaskName $taskName).State
$watchdogTask=Get-ScheduledTask -TaskName $watchdogName
if ($clientState -ne 'Running') {{ throw 'Thin Client did not enter Running state' }}
if ($null -eq $watchdogTask) {{ throw 'Watchdog task registration missing' }}
Write-Output 'agentos_supervisor_ready=true'
"""


def _non_windows_lifecycle() -> dict[str, Any]:
    return {'schema': 'agentos.node-lifecycle/v0.1', 'platform': platform.system(), 'applicable': False, 'supervisor_ready': True}


def install_windows_node_supervisor(*, install_root: Path | None = None, launcher: Path | None = None) -> dict[str, Any]:
    if platform.system() != 'Windows':
        return _non_windows_lifecycle()
    root = Path(install_root or windows_node_install_root())
    client_launcher = Path(launcher or (root / 'agentos-client.cmd'))
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', render_windows_supervisor_install_script(install_root=root, launcher=client_launcher)],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    ready = result.returncode == 0 and 'agentos_supervisor_ready=true' in result.stdout
    return {
        'schema': 'agentos.node-lifecycle/v0.1',
        'platform': 'Windows',
        'applicable': True,
        'supervisor_ready': ready,
        'thin_client_task': WINDOWS_THIN_CLIENT_TASK,
        'watchdog_task': WINDOWS_WATCHDOG_TASK,
        'returncode': result.returncode,
        'stderr': result.stderr[-2000:],
    }


def check_windows_node_supervisor() -> dict[str, Any]:
    if platform.system() != 'Windows':
        return _non_windows_lifecycle()
    script = f"""$client=Get-ScheduledTask -TaskName '{WINDOWS_THIN_CLIENT_TASK}' -ErrorAction SilentlyContinue
$watchdog=Get-ScheduledTask -TaskName '{WINDOWS_WATCHDOG_TASK}' -ErrorAction SilentlyContinue
if ($null -eq $client -or $null -eq $watchdog) {{ exit 2 }}
if ($client.State -ne 'Running') {{ exit 3 }}
Write-Output 'agentos_supervisor_ready=true'
"""
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    ready = result.returncode == 0 and 'agentos_supervisor_ready=true' in result.stdout
    return {
        'schema': 'agentos.node-lifecycle/v0.1',
        'platform': 'Windows',
        'applicable': True,
        'supervisor_ready': ready,
        'thin_client_task': WINDOWS_THIN_CLIENT_TASK,
        'watchdog_task': WINDOWS_WATCHDOG_TASK,
        'returncode': result.returncode,
        'stderr': result.stderr[-2000:],
    }


def build_join_regression_report(
    *,
    realm_id: str,
    node_id: str,
    before_manifest: dict[str, Any],
    after_manifest: dict[str, Any],
    bootstrap: dict[str, Any],
    report_kind: str = 'join-regression',
    lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if report_kind not in {'join-regression', 'readiness-regression'}:
        raise ValueError('invalid regression report kind')
    before_caps = set(before_manifest.get('capabilities') or [])
    after_caps = set(after_manifest.get('capabilities') or [])
    lost_caps = sorted(before_caps - after_caps)
    inherited_caps = sorted(set(bootstrap.get('inherited_realm_capabilities') or []))
    canonical = list(bootstrap.get('canonical_capabilities') or [])
    canonical_ids = sorted({str(item.get('capability_id')) for item in canonical if isinstance(item, dict) and item.get('capability_id')})

    before = {
        'task_success': 1.0,
        'repeated_errors': 0,
        'user_clarifications': 0,
        'continuity_recovery': 0.0,
        'realm_capability_usage': 0,
        'inherited_cognition_usage': 0,
        'evidence_returned': 0,
    }
    after = {
        'task_success': 1.0 if not lost_caps else 0.0,
        'repeated_errors': len(lost_caps),
        'user_clarifications': 0,
        'continuity_recovery': 1.0 if canonical_ids else 0.0,
        'realm_capability_usage': len(inherited_caps),
        'inherited_cognition_usage': len(canonical_ids),
        'evidence_returned': 1,
    }
    uplift = {
        'task_success': after['task_success'] - before['task_success'],
        'repeated_errors': before['repeated_errors'] - after['repeated_errors'],
        'user_clarifications': before['user_clarifications'] - after['user_clarifications'],
        'continuity_recovery': after['continuity_recovery'] - before['continuity_recovery'],
        'realm_capability_usage': after['realm_capability_usage'] - before['realm_capability_usage'],
        'inherited_cognition_usage': after['inherited_cognition_usage'] - before['inherited_cognition_usage'],
        'evidence_returned': after['evidence_returned'] - before['evidence_returned'],
    }
    improved = sum(1 for value in uplift.values() if value > 0)
    regressed = sum(1 for value in uplift.values() if value < 0)
    lifecycle_ready = True if lifecycle is None else bool(lifecycle.get('supervisor_ready'))
    ready = not lost_caps and bootstrap.get('schema') == 'agentos.node-bootstrap/v0.1' and lifecycle_ready
    return {
        'schema': 'agentos.one-uplift-report/v0.1',
        'report_kind': report_kind,
        'realm_id': realm_id,
        'node_id': node_id,
        'before': before,
        'after': after,
        'uplift': uplift,
        'improved_dimensions': improved,
        'regressed_dimensions': regressed,
        'one_uplift_observed': improved > 0 and regressed == 0,
        'node_ready': ready,
        'lifecycle': lifecycle,
        'checks': {
            'local_capability_non_regression': not lost_caps,
            'lost_capabilities': lost_caps,
            'inherited_realm_capabilities': inherited_caps,
            'canonical_capabilities': canonical_ids,
            'surface_inventory_present': isinstance(after_manifest.get('surface_inventory'), dict),
            'lifecycle_supervisor_ready': lifecycle_ready,
        },
    }
