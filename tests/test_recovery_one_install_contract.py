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

    def test_canonical_installer_publishes_probe_as_source_payload(self):
        script = PINNED_PAYLOAD.read_text(encoding="utf-8")
        self.assertIn("'scripts/windows/recovery_one_probe.py'", script)
        self.assertIn("'scripts/windows/recovery_slot_runner.py'", script)
        self.assertTrue(RECOVERY.is_file())

    def test_recovery_has_no_install_execute_or_command_channel(self):
        script = RECOVERY.read_text(encoding="utf-8")
        self.assertIn('method="GET"', script)
        self.assertIn('NoRecoveryRedirect', script)
        self.assertNotIn("subprocess", script)
        self.assertNotIn("shell.exec", script)
        self.assertNotIn("os.system", script)


if __name__ == "__main__":
    unittest.main()
