from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EmployeeWorkerHostInstallerRuntimeTests(unittest.TestCase):
    def _fixture(self, *, enable: bool, create_wake_root: bool = True) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str], Path]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name) / "agentmanager"
        (root / "scripts").mkdir(parents=True)
        (root / ".agent" / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts" / "install_systemd_user.sh", root / "scripts" / "install_systemd_user.sh")
        for name in (
            "agentos-core-supervisor.service",
            "agentos-core-supervisor-delivery.conf.example",
            "agentos-employee-worker-host.service",
        ):
            shutil.copy2(ROOT / ".agent" / "scripts" / name, root / ".agent" / "scripts" / name)

        home = Path(td.name) / "home"
        fakebin = Path(td.name) / "bin"
        fakebin.mkdir()
        systemctl_log = Path(td.name) / "systemctl.log"
        systemctl = fakebin / "systemctl"
        systemctl.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\nexit 0\n",
            encoding="utf-8",
        )
        systemctl.chmod(0o755)

        data_root = Path(td.name) / "data"
        wake_root = Path(td.name) / "wake-inbox"
        if create_wake_root:
            wake_root.mkdir(parents=True)
        lines = [
            "AGENT_MODE=CORE",
            f"AGENT_DATA_ROOT={data_root}",
            f"AGENTOS_EMPLOYEE_WAKE_ROOT={wake_root}",
            "AGENTOS_EMPLOYEE_WORKER_NODE_ID=oracle-core",
        ]
        if enable:
            lines.append("AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE=1")
        (root / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "PATH": f"{fakebin}:{env.get('PATH', '')}",
                "SYSTEMCTL_LOG": str(systemctl_log),
            }
        )
        return td, root, env, wake_root

    @staticmethod
    def _run(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(root / "scripts" / "install_systemd_user.sh")],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_default_core_install_keeps_worker_host_disabled(self):
        td, root, env, _ = self._fixture(enable=False)
        self.addCleanup(td.cleanup)
        result = self._run(root, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        home = Path(env["HOME"])
        self.assertFalse((home / ".config" / "agentos" / "employee-worker-host.env").exists())
        log = Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")
        self.assertIn("--user disable --now agentos-employee-worker-host.service", log)
        self.assertNotIn("--user enable agentos-employee-worker-host.service", log)

    def test_enabled_install_requires_existing_wake_root(self):
        td, root, env, wake_root = self._fixture(enable=True, create_wake_root=False)
        self.addCleanup(td.cleanup)
        self.assertFalse(wake_root.exists())
        result = self._run(root, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("configured wake root does not already exist", result.stderr)
        self.assertFalse(wake_root.exists())

    def test_enabled_install_renders_shared_service_and_env(self):
        td, root, env, wake_root = self._fixture(enable=True)
        self.addCleanup(td.cleanup)
        result = self._run(root, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        home = Path(env["HOME"])
        unit = (home / ".config" / "systemd" / "user" / "agentos-employee-worker-host.service").read_text(encoding="utf-8")
        worker_env = (home / ".config" / "agentos" / "employee-worker-host.env").read_text(encoding="utf-8")
        self.assertIn(f"WorkingDirectory={root}", unit)
        self.assertIn(f"ReadOnlyPaths={wake_root}", unit)
        self.assertIn("PrivateNetwork=true", unit)
        self.assertIn(f"AGENTOS_EMPLOYEE_WAKE_ROOT={wake_root}", worker_env)
        self.assertIn("AGENTOS_EMPLOYEE_WORKER_NODE_ID=oracle-core", worker_env)
        self.assertNotIn("TOKEN", worker_env.upper())
        log = Path(env["SYSTEMCTL_LOG"]).read_text(encoding="utf-8")
        self.assertIn("--user enable agentos-employee-worker-host.service", log)
        self.assertIn("--user restart agentos-employee-worker-host.service", log)


if __name__ == "__main__":
    unittest.main()
