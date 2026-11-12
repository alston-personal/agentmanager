from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONE_CLICK = ROOT / "install-agentos.ps1"
PINNED_PAYLOAD = ROOT / "scripts/install_thin_client_windows.ps1"
RECOVERY = ROOT / "scripts/windows/recovery_one_probe.py"


class CanonicalRecoveryInstallationTests(unittest.TestCase):
    def test_one_click_installs_separate_read_only_probe_after_join_and_verify(self):
        script = ONE_CLICK.read_text(encoding="utf-8")
        self.assertIn("function Install-RecoveryProbe(", script)
        self.assertIn("recovery_one_probe.py", script)
        self.assertIn("AgentOS Recovery ONE Probe", script)
        self.assertIn("one_transport_roundtrip", script)
        self.assertIn("recovery_update_authorized", script)
        self.assertIn("Register-ScheduledTask -TaskName $recoveryTaskName", script)
        self.assertLess(script.index("Install-Supervisor $python.Path $runtimeRoot"),
                        script.index("Install-RecoveryProbe $python.Path $runtimeRoot"))
        self.assertLess(script.index("AgentOS readiness verification failed"),
                        script.index("Install-RecoveryProbe $python.Path $runtimeRoot"))

    def test_normal_reinstall_cannot_overwrite_recovery_image(self):
        script = ONE_CLICK.read_text(encoding="utf-8")
        self.assertIn("if(-not (Test-Path -LiteralPath $runner))", script)
        self.assertIn("Existing Recovery launcher retained; normal install cannot upgrade it.", script)
        self.assertIn("--bootstrap-from $bootstrapSource", script)
        self.assertIn("slot_runner.py", script)
        self.assertIn("Join-Path $InstallRoot 'recovery'", script)
        self.assertNotIn("Remove-Item -Recurse -Force $recoveryRoot", script)

    def test_normal_reinstall_does_not_rebind_existing_recovery_scheduled_task(self):
        script = ONE_CLICK.read_text(encoding="utf-8")
        self.assertIn("Get-ScheduledTask -TaskName $recoveryTaskName", script)
        self.assertIn("if($existingRecoveryTask)", script)
        self.assertIn("Existing Recovery scheduled task retained", script)
        self.assertIn("$existingActions[0].Execute", script)
        self.assertIn("protected launcher; no automatic takeover", script)
        self.assertIn("including its independent Python executable and triggers", script)
        self.assertIn("--diagnose-lkg-when-pending-corrupt", script)
        # Existing tasks must be validated BEFORE the live probe, and the
        # probe must use the exact executable preserved by Task Scheduler.
        self.assertIn("$recoveryPythonPath = $PythonPath", script)
        self.assertIn("$recoveryPythonPath = (Resolve-Path -LiteralPath $existingExecute).Path", script)
        self.assertIn("& $recoveryPythonPath -I $runner --root $recoveryRoot --bootstrap-from", script)
        self.assertIn("& $recoveryPythonPath -I $runner --root $recoveryRoot --config", script)
        self.assertIn("New-ScheduledTaskAction -Execute $recoveryPythonPath", script)
        self.assertLess(
            script.index("$recoveryPythonPath = (Resolve-Path -LiteralPath $existingExecute).Path"),
            script.index("& $recoveryPythonPath -I $runner --root $recoveryRoot --config")
        )
        self.assertNotIn("& $PythonPath -I $runner", script)
        installer = script[script.index("function Install-RecoveryProbe("):
                           script.index("\ntry {\n  if($env:OS -ne 'Windows_NT')")]
        self.assertEqual(installer.count("Register-ScheduledTask -TaskName $recoveryTaskName"), 1)
        self.assertNotIn("Register-ScheduledTask -TaskName $recoveryTaskName -Action $action -Trigger @($logon,$periodic) -Settings $settings -Force", installer)

    def test_canonical_installer_publishes_probe_as_source_payload(self):
        script = PINNED_PAYLOAD.read_text(encoding="utf-8")
        self.assertIn("'scripts/windows/recovery_one_probe.py'", script)
        self.assertIn("'scripts/windows/recovery_slot_runner.py'", script)
        self.assertTrue(RECOVERY.is_file())

    def test_offline_recovery_python_requires_explicit_archive_and_trusted_hash(self):
        script = ONE_CLICK.read_text(encoding="utf-8")
        self.assertIn("[string]$RecoveryPythonArchive", script)
        self.assertIn("[string]$RecoveryPythonSha256", script)
        self.assertIn("if(-not $existingRecoveryTask)", script)
        self.assertIn("install_recovery_python.ps1", script)
        self.assertIn("-ExpectedSha256 $RecoveryPythonSha256", script)
        self.assertIn("Existing Recovery Python can only be upgraded by the authorized Recovery updater.", script)
        self.assertIn("Both RecoveryPythonArchive and RecoveryPythonSha256 are required.", script)
        self.assertIn("python-runtime", script)
        self.assertIn("$action = New-ScheduledTaskAction -Execute $recoveryPythonPath", script)
        payload = PINNED_PAYLOAD.read_text(encoding="utf-8")
        self.assertIn("'scripts/windows/install_recovery_python.ps1'", payload)
        provision = (ROOT / "scripts/windows/install_recovery_python.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-FileHash", provision)
        self.assertIn("RECOVERY_RUNTIME_ARCHIVE_HASH_MISMATCH", provision)
        self.assertIn("RECOVERY_RUNTIME_ALREADY_EXISTS_NEEDS_AUTHORIZED_UPDATE", provision)
        self.assertIn("RECOVERY_RUNTIME_ARCHIVE_UNSAFE_ENTRY", provision)
        self.assertNotIn("Invoke-WebRequest", provision)
        self.assertNotIn("Start-BitsTransfer", provision)

    def test_recovery_has_no_install_execute_or_command_channel(self):
        script = RECOVERY.read_text(encoding="utf-8")
        self.assertIn('method="GET"', script)
        self.assertIn('NoRecoveryRedirect', script)
        self.assertNotIn("subprocess", script)
        self.assertNotIn("shell.exec", script)
        self.assertNotIn("os.system", script)


if __name__ == "__main__":
    unittest.main()
