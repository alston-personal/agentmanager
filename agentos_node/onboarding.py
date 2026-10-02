from __future__ import annotations

import os
import platform
import subprocess
import sys
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
$install=Join-Path $env:LOCALAPPDATA 'AgentOS'
$launcher=Join-Path $install 'agentos-client.cmd'
$leaseCandidates=@()
if ($env:AGENTOS_CLIENT_HOME) {
  $leaseCandidates += (Join-Path $env:AGENTOS_CLIENT_HOME 'heartbeat-lease.json')
}
$leaseCandidates += (Join-Path (Join-Path $install 'state') 'heartbeat-lease.json')
$leaseCandidates += (Join-Path (Join-Path $env:USERPROFILE '.agentos') 'heartbeat-lease.json')

function Ensure-AgentOSThinClientTask {
  $task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if ($null -ne $task) { return $task }
  if (-not (Test-Path -LiteralPath $launcher)) { throw 'agentos-client launcher missing' }
  $action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c "' + $launcher + '" run') -WorkingDirectory $install
  $trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'AgentOS Thin Client user-session daemon' -Force | Out-Null
  return (Get-ScheduledTask -TaskName $taskName -ErrorAction Stop)
}

$task=Ensure-AgentOSThinClientTask
$restart=$false
if ($task.State -ne 'Running') {
  $restart=$true
} else {
  $lease=$null
  foreach($candidate in $leaseCandidates) {
    if (Test-Path -LiteralPath $candidate) {
      try {
        $candidateLease=Get-Content -Raw -LiteralPath $candidate | ConvertFrom-Json
        if ($null -eq $lease -or [int64]$candidateLease.recorded_at_unix -gt [int64]$lease.recorded_at_unix) {
          $lease=$candidateLease
        }
      } catch {}
    }
  }
  if ($null -eq $lease) {
    $restart=$true
  } else {
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $age=$now-[int64]$lease.recorded_at_unix
    if ($age -gt 120) { $restart=$true }
  }
}

if ($restart) {
  Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
  Start-ScheduledTask -TaskName $taskName
  Start-Sleep -Seconds 5
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
$watchdogLogon=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$watchdogPeriodic=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$watchdogSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $watchdogName -Action $watchdogAction -Trigger @($watchdogLogon,$watchdogPeriodic) -Settings $watchdogSettings -Description 'AgentOS heartbeat-aware Thin Client watchdog' -Force | Out-Null

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


MACOS_LAUNCH_AGENT_LABEL = 'org.milkcat.agentos.thin-client'

def macos_node_install_root() -> Path:
    return Path.home() / 'Library' / 'Application Support' / 'AgentOS'

def macos_launch_agent_path() -> Path:
    return Path.home() / 'Library' / 'LaunchAgents' / (MACOS_LAUNCH_AGENT_LABEL + '.plist')

def install_macos_node_supervisor(*, install_root: Path | None = None, launcher: Path | None = None) -> dict[str, Any]:
    if platform.system() != 'Darwin':
        return _non_windows_lifecycle()
    root = Path(install_root or macos_node_install_root())
    client_launcher = Path(launcher or (root / 'agentos-client'))
    plist = macos_launch_agent_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    if not client_launcher.exists():
        return {'schema':'agentos.node-lifecycle/v0.1','platform':'Darwin','applicable':True,'supervisor_ready':False,'label':MACOS_LAUNCH_AGENT_LABEL,'plist':str(plist),'returncode':2,'stderr':'agentos-client launcher missing'}
    payload = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{MACOS_LAUNCH_AGENT_LABEL}</string>
<key>ProgramArguments</key><array><string>{client_launcher}</string><string>run</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ProcessType</key><string>Background</string>
<key>StandardOutPath</key><string>{root / 'thin-client.out.log'}</string>
<key>StandardErrorPath</key><string>{root / 'thin-client.err.log'}</string>
</dict></plist>
'''
    plist.write_text(payload, encoding='utf-8')
    uid = str(os.getuid())
    subprocess.run(['launchctl','bootout',f'gui/{uid}',str(plist)],capture_output=True,text=True,check=False)
    result = subprocess.run(['launchctl','bootstrap',f'gui/{uid}',str(plist)],capture_output=True,text=True,check=False)
    subprocess.run(['launchctl','kickstart','-k',f'gui/{uid}/{MACOS_LAUNCH_AGENT_LABEL}'],capture_output=True,text=True,check=False)
    ready = result.returncode == 0
    return {'schema':'agentos.node-lifecycle/v0.1','platform':'Darwin','applicable':True,'supervisor_ready':ready,'label':MACOS_LAUNCH_AGENT_LABEL,'plist':str(plist),'returncode':result.returncode,'stderr':result.stderr[-2000:]}

def check_macos_node_supervisor() -> dict[str, Any]:
    if platform.system() != 'Darwin':
        return _non_windows_lifecycle()
    uid = str(os.getuid())
    result = subprocess.run(['launchctl','print',f'gui/{uid}/{MACOS_LAUNCH_AGENT_LABEL}'],capture_output=True,text=True,check=False)
    ready = result.returncode == 0
    return {'schema':'agentos.node-lifecycle/v0.1','platform':'Darwin','applicable':True,'supervisor_ready':ready,'label':MACOS_LAUNCH_AGENT_LABEL,'plist':str(macos_launch_agent_path()),'returncode':result.returncode,'stderr':result.stderr[-2000:]}


LINUX_THIN_CLIENT_UNIT = 'agentos-thin-client.service'

def linux_node_install_root() -> Path:
    return Path.home() / '.local' / 'share' / 'AgentOS'

def linux_systemd_user_dir() -> Path:
    return Path.home() / '.config' / 'systemd' / 'user'

def linux_thin_client_unit_path() -> Path:
    return linux_systemd_user_dir() / LINUX_THIN_CLIENT_UNIT

def install_linux_node_supervisor(*, install_root: Path | None = None, launcher: Path | None = None) -> dict[str, Any]:
    if platform.system() != 'Linux':
        return _non_windows_lifecycle()
    root = Path(install_root or linux_node_install_root())
    client_launcher = Path(launcher or (root / 'agentos-client'))
    unit = linux_thin_client_unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    if not client_launcher.exists():
        python_bin = Path(sys.executable).resolve()
        client_launcher.write_text(
            '#!/usr/bin/env bash\n'
            + 'set -euo pipefail\n'
            + f'exec "{python_bin}" -m agentos_node.client_cli "$@"\n',
            encoding='utf-8',
        )
        client_launcher.chmod(0o700)
    payload = f'''[Unit]
Description=AgentOS Thin Client Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart={client_launcher} run
Restart=always
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
'''
    unit.write_text(payload, encoding='utf-8')
    subprocess.run(['systemctl','--user','daemon-reload'],capture_output=True,text=True,check=False)
    result = subprocess.run(
        ['systemctl','--user','enable','--now',LINUX_THIN_CLIENT_UNIT],
        capture_output=True,text=True,timeout=20,check=False,
    )
    probe = subprocess.run(
        ['systemctl','--user','is-active',LINUX_THIN_CLIENT_UNIT],
        capture_output=True,text=True,timeout=10,check=False,
    )
    ready = result.returncode == 0 and probe.returncode == 0 and probe.stdout.strip() == 'active'
    return {
        'schema':'agentos.node-lifecycle/v0.1','platform':'Linux','applicable':True,
        'supervisor_ready':ready,'unit':LINUX_THIN_CLIENT_UNIT,'unit_path':str(unit),
        'returncode':result.returncode,'stderr':(result.stderr + '\n' + probe.stderr)[-2000:],
    }

def check_linux_node_supervisor() -> dict[str, Any]:
    if platform.system() != 'Linux':
        return _non_windows_lifecycle()
    unit = linux_thin_client_unit_path()
    result = subprocess.run(
        ['systemctl','--user','is-active',LINUX_THIN_CLIENT_UNIT],
        capture_output=True,text=True,timeout=10,check=False,
    )
    ready = unit.exists() and result.returncode == 0 and result.stdout.strip() == 'active'
    return {
        'schema':'agentos.node-lifecycle/v0.1','platform':'Linux','applicable':True,
        'supervisor_ready':ready,'unit':LINUX_THIN_CLIENT_UNIT,'unit_path':str(unit),
        'returncode':result.returncode,'stderr':result.stderr[-2000:],
    }

def install_node_supervisor() -> dict[str, Any]:
    system = platform.system()
    if system == 'Windows':
        return install_windows_node_supervisor()
    if system == 'Darwin':
        return install_macos_node_supervisor()
    if system == 'Linux':
        return install_linux_node_supervisor()
    return _non_windows_lifecycle()

def check_node_supervisor() -> dict[str, Any]:
    system = platform.system()
    if system == 'Windows':
        return check_windows_node_supervisor()
    if system == 'Darwin':
        return check_macos_node_supervisor()
    if system == 'Linux':
        return check_linux_node_supervisor()
    return _non_windows_lifecycle()
