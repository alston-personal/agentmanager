param(
  [string]$ServiceName = 'AgentOSNodeRuntime',
  [string]$DisplayName = 'AgentOS Node Runtime',
  [string]$InstallRoot = "$env:LOCALAPPDATA\AgentOS",
  [string]$LegacyTaskName = 'AgentOS Thin Client',
  [string]$BridgeRoot = "$env:ProgramData\AgentOS\executor-bridges\desktop-$env:USERNAME"
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Administrator privileges are required to install the AgentOS Node Runtime Windows Service.'
}

$launcher = Join-Path $InstallRoot 'agentos-client.cmd'
$stateRoot = Join-Path $InstallRoot 'state'
if (-not (Test-Path $launcher)) { throw "Missing AgentOS launcher: $launcher" }
if (-not (Test-Path (Join-Path $stateRoot 'client.json'))) { throw "Missing enrolled node config under $stateRoot" }
if (-not (Test-Path (Join-Path $stateRoot 'policy.json'))) { throw "Missing node policy under $stateRoot" }

$runtimeRoot = Join-Path $env:ProgramData 'AgentOS\node-runtime'
New-Item -ItemType Directory -Force -Path $runtimeRoot, $BridgeRoot | Out-Null

# The bridge is a local authority boundary shared only by SYSTEM/Administrators and
# the currently logged-in user that hosts the interactive desktop executor.
$currentUser = $identity.Name
& icacls.exe $BridgeRoot /inheritance:r | Out-Null
& icacls.exe $BridgeRoot /grant:r 'SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F' "$currentUser`:(OI)(CI)M" | Out-Null

$serviceExe = Join-Path $runtimeRoot 'AgentOSNodeRuntimeService.exe'
$escapedLauncher = $launcher.Replace('"', '""')
$escapedInstall = $InstallRoot.Replace('"', '""')
$escapedBridge = $BridgeRoot.Replace('"', '""')

$source = @'
using System;
using System.Diagnostics;
using System.ServiceProcess;
using System.Threading;

public sealed class AgentOSNodeRuntimeService : ServiceBase
{
    private readonly object gate = new object();
    private Timer timer;
    private Process child;
    private bool stopping;

    private const string Launcher = @"__LAUNCHER__";
    private const string WorkingRoot = @"__INSTALL_ROOT__";
    private const string DesktopBridge = @"__BRIDGE_ROOT__";

    public AgentOSNodeRuntimeService()
    {
        ServiceName = "AgentOSNodeRuntime";
        CanStop = true;
        CanShutdown = true;
        AutoLog = true;
    }

    protected override void OnStart(string[] args)
    {
        stopping = false;
        timer = new Timer(EnsureChild, null, TimeSpan.Zero, TimeSpan.FromSeconds(5));
    }

    protected override void OnStop()
    {
        stopping = true;
        if (timer != null) timer.Dispose();
        lock (gate)
        {
            StopChild();
        }
    }

    protected override void OnShutdown()
    {
        OnStop();
        base.OnShutdown();
    }

    private void EnsureChild(object state)
    {
        if (stopping) return;
        lock (gate)
        {
            if (stopping) return;
            if (child != null && !child.HasExited) return;
            if (child != null)
            {
                child.Dispose();
                child = null;
            }
            var psi = new ProcessStartInfo();
            psi.FileName = "cmd.exe";
            psi.Arguments = "/d /c \"\"" + Launcher + "\" run\"";
            psi.WorkingDirectory = WorkingRoot;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.EnvironmentVariables["AGENTOS_DESKTOP_EXECUTOR_BRIDGE"] = DesktopBridge;
            child = Process.Start(psi);
        }
    }

    private void StopChild()
    {
        if (child == null) return;
        try
        {
            if (!child.HasExited)
            {
                child.Kill();
                child.WaitForExit(5000);
            }
        }
        catch { }
        finally
        {
            child.Dispose();
            child = null;
        }
    }

    public static void Main()
    {
        ServiceBase.Run(new AgentOSNodeRuntimeService());
    }
}
'@
$source = $source.Replace('__LAUNCHER__', $escapedLauncher).Replace('__INSTALL_ROOT__', $escapedInstall).Replace('__BRIDGE_ROOT__', $escapedBridge)

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
  if ($existing.Status -ne 'Stopped') {
    Stop-Service -Name $ServiceName -Force
    $existing.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(15))
  }
  & sc.exe delete $ServiceName | Out-Null
  Start-Sleep -Seconds 1
}
if (Test-Path $serviceExe) { Remove-Item -Force $serviceExe }

Add-Type -TypeDefinition $source -Language CSharp -ReferencedAssemblies 'System.ServiceProcess.dll' -OutputAssembly $serviceExe -OutputType WindowsApplication
if (-not (Test-Path $serviceExe)) { throw 'Windows Service wrapper compilation failed.' }

& sc.exe create $ServiceName "binPath= `"$serviceExe`"" 'start= auto' "DisplayName= $DisplayName" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "sc.exe create failed for $ServiceName" }
& sc.exe failure $ServiceName 'reset= 86400' 'actions= restart/5000/restart/5000/restart/10000' | Out-Null
& sc.exe failureflag $ServiceName 1 | Out-Null

$legacyTask = Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
if ($legacyTask) {
  Stop-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
}

Start-Service -Name $ServiceName
$service = Get-Service -Name $ServiceName
$service.WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
if ($service.Status -ne 'Running') {
  if ($legacyTask) { Start-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue }
  throw "$ServiceName did not reach Running state; legacy task was restarted when available."
}

if ($legacyTask) {
  Disable-ScheduledTask -TaskName $LegacyTaskName | Out-Null
}

Write-Host "AgentOS Node Runtime Windows Service: $($service.Status)"
Write-Host "Service name: $ServiceName"
Write-Host "Desktop executor bridge: $BridgeRoot"
if ($legacyTask) { Write-Host "Legacy task retained but disabled for rollback: $LegacyTaskName" }
Write-Host 'No Realm credential value was printed or copied by this installer.'
