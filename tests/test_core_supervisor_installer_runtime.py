from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CoreSupervisorInstallerRuntimeTests(unittest.TestCase):
    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str]]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name) / "agentmanager"
        (root / "scripts").mkdir(parents=True)
        (root / ".agent" / "scripts").mkdir(parents=True)
        shutil.copy2(ROOT / "scripts" / "install_systemd_user.sh", root / "scripts" / "install_systemd_user.sh")
        for name in (
            "agentos-core-supervisor.service",
            "agentos-core-supervisor-delivery.conf.example",
        ):
            shutil.copy2(ROOT / ".agent" / "scripts" / name, root / ".agent" / "scripts" / name)

        home = Path(td.name) / "home"
        fakebin = Path(td.name) / "bin"
        fakebin.mkdir()
        systemctl = fakebin / "systemctl"
        systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        systemctl.chmod(0o755)

        data_root = Path(td.name) / "data"
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "PATH": f"{fakebin}:{env.get('PATH', '')}",
            }
        )
        self._write_env(root, data_root, one_direct=False)
        return td, root, env

    @staticmethod
    def _write_env(root: Path, data_root: Path, *, one_direct: bool) -> None:
        lines = ["AGENT_MODE=CORE", f"AGENT_DATA_ROOT={data_root}"]
        if one_direct:
            lines.append("AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1")
        (root / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

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

    def test_core_install_renders_user_supervisor_and_defaults_s3(self):
        td, root, env = self._fixture()
        self.addCleanup(td.cleanup)
        result = self._run(root, env)
        self.assertEqual(result.returncode, 0, result.stderr)

        home = Path(env["HOME"])
        unit = (home / ".config" / "systemd" / "user" / "agentos-core-supervisor.service").read_text(encoding="utf-8")
        supervisor_env = (home / ".config" / "agentos" / "core-supervisor.env").read_text(encoding="utf-8")
        self.assertNotIn("User=ubuntu", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn(f"WorkingDirectory={root}", unit)
        self.assertIn(f"ReadWritePaths={Path(td.name) / 'data' / 'employee-runtime'}", unit)
        self.assertIn("PrivateNetwork=true", unit)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled", supervisor_env)
        self.assertFalse((home / ".config" / "agentos" / "core-supervisor-delivery.env").exists())

    def test_one_direct_fails_closed_without_existing_one_state(self):
        td, root, env = self._fixture()
        self.addCleanup(td.cleanup)
        data_root = Path(td.name) / "data"
        self._write_env(root, data_root, one_direct=True)
        result = self._run(root, env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing existing", result.stderr)
        self.assertFalse((data_root / "realm" / "fabric.json").exists())
        self.assertFalse((data_root / "realm" / "nodes.json").exists())

    def test_explicit_one_direct_renders_narrow_dropin_and_delivery_env(self):
        td, root, env = self._fixture()
        self.addCleanup(td.cleanup)
        data_root = Path(td.name) / "data"
        realm = data_root / "realm"
        realm.mkdir(parents=True)
        (realm / "fabric.json").write_text("{}\n", encoding="utf-8")
        (realm / "nodes.json").write_text("{}\n", encoding="utf-8")
        self._write_env(root, data_root, one_direct=True)

        result = self._run(root, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        home = Path(env["HOME"])
        delivery_env = (home / ".config" / "agentos" / "core-supervisor-delivery.env").read_text(encoding="utf-8")
        dropin = (
            home
            / ".config"
            / "systemd"
            / "user"
            / "agentos-core-supervisor.service.d"
            / "20-one-direct-filesystem.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct", delivery_env)
        self.assertIn(f"AGENTOS_SUPERVISOR_ONE_DATA_ROOT={data_root}", delivery_env)
        self.assertIn(f"ReadWritePaths={realm}", dropin)
        self.assertNotIn("PrivateNetwork=false", dropin)

    def test_existing_host_env_is_preserved(self):
        td, root, env = self._fixture()
        self.addCleanup(td.cleanup)
        host_env = Path(env["HOME"]) / ".config" / "agentos" / "core-supervisor.env"
        host_env.parent.mkdir(parents=True)
        sentinel = "AGENTOS_EMPLOYEE_RUNTIME_ROOT=/custom/runtime\nAGENTOS_SUPERVISOR_DELIVERY_MODE=disabled\nCUSTOM_SENTINEL=keep\n"
        host_env.write_text(sentinel, encoding="utf-8")
        result = self._run(root, env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(host_env.read_text(encoding="utf-8"), sentinel)


if __name__ == "__main__":
    unittest.main()
