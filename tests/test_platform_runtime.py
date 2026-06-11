from __future__ import annotations

import json
import os
import subprocess
import sys
import signal
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class PlatformRuntimeSmokeTests(unittest.TestCase):
    def _run(self, script: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / script), *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_platform_runtime_selection_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = os.environ.copy()
            env["AGENT_DATA_ROOT"] = str(base / "agent-data")
            linux = self._run(
                "scripts/platform_runtime.py",
                ["--platform", "linux", "--project-root", str(base / "project"), "--data-root", str(base / "agent-data"), "info"],
                env,
            )
            self.assertEqual(linux.returncode, 0, linux.stderr)
            linux_payload = json.loads(linux.stdout)
            self.assertEqual(linux_payload["platform"], "linux")
            self.assertTrue(linux_payload["runtime_dir"].endswith("runtime"))

            windows = self._run(
                "scripts/platform_runtime.py",
                ["--platform", "windows", "--project-root", str(base / "project"), "--data-root", str(base / "agent-data"), "info"],
                env,
            )
            self.assertEqual(windows.returncode, 0, windows.stderr)
            windows_payload = json.loads(windows.stdout)
            self.assertEqual(windows_payload["platform"], "windows")
            self.assertTrue(windows_payload["runtime_dir"].endswith("runtime"))

    def test_install_services_entrypoint_on_linux_and_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = os.environ.copy()
            env["AGENT_DATA_ROOT"] = str(base / "agent-data")
            env["PATH"] = ""

            linux = self._run(
                "scripts/install_services.py",
                ["--platform", "linux", "--project-root", str(base / "project"), "--data-root", str(base / "agent-data")],
                env,
            )
            self.assertEqual(linux.returncode, 0, linux.stderr)
            self.assertIn('"platform": "linux"', linux.stdout)
            self.assertTrue((base / "agent-data" / "runtime" / "services" / "manifest.json").exists())

            windows = self._run(
                "scripts/install_services.py",
                ["--platform", "windows", "--project-root", str(base / "project"), "--data-root", str(base / "agent-data")],
                env,
            )
            self.assertEqual(windows.returncode, 0, windows.stderr)
            self.assertIn('"platform": "windows"', windows.stdout)
            self.assertTrue((base / "agent-data" / "runtime" / "services" / "manifest.json").exists())

    def test_pulse_smoke_on_linux_and_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = os.environ.copy()
            env["AGENT_DATA_ROOT"] = str(base / "agent-data")
            env["PATH"] = ""

            linux = self._run(
                "scripts/pulse.py",
                ["--platform", "linux", "--agent", "Test", "--task", "x", "--status", "active"],
                env,
            )
            self.assertEqual(linux.returncode, 0, linux.stderr)
            self.assertIn("Pulsed: Test", linux.stdout)

            windows = self._run(
                "scripts/pulse.py",
                ["--platform", "windows", "--agent", "Test", "--task", "x", "--status", "active"],
                env,
            )
            self.assertEqual(windows.returncode, 0, windows.stderr)
            self.assertIn("Pulsed: Test", windows.stdout)

    def test_schedule_recurring_job_starts_runner_on_windows_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = os.environ.copy()
            env["AGENT_DATA_ROOT"] = str(base / "agent-data")
            from agent_core.platform import get_platform_driver

            driver = get_platform_driver(
                "windows",
                project_root=base / "project",
                data_root=base / "agent-data",
            )
            payload = driver.schedule_recurring_job("test-job", [sys.executable, "-c", "print('runner-ok')"], 60)
            self.assertEqual(payload["name"], "test-job")
            self.assertEqual(payload["platform"], "windows")
            self.assertIn("runner_pid", payload)
            self.assertTrue((base / "agent-data" / "runtime" / "services" / "scheduled_jobs.json").exists())
            self.assertTrue((base / "agent-data" / "runtime" / "services" / "runtime" / "test-job.runner.json").exists())
            pid = payload.get("runner_pid")
            if isinstance(pid, int) and pid > 0:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
