from __future__ import annotations

import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

from scripts import install_services


class StrictInstallServicesTests(unittest.TestCase):
    def _run(self, *, result: dict, platform: str = "linux", env: dict[str, str] | None = None):
        driver = Mock()
        driver.platform_name.return_value = platform
        driver.install_background_services.return_value = result
        output = StringIO()
        with (
            patch.object(install_services, "get_platform_driver", return_value=driver),
            patch.object(sys, "argv", ["install_services.py"]),
            patch.dict(os.environ, env or {}, clear=True),
            redirect_stdout(output),
        ):
            rc = install_services.main()
        return rc, output.getvalue()

    def test_attempted_systemd_failure_is_never_reported_success(self):
        rc, output = self._run(
            result={
                "installed": 0,
                "mode": "fallback-manifest",
                "systemd_returncode": 2,
                "systemd_stderr": "private detail not asserted",
            }
        )
        self.assertEqual(rc, 2)
        self.assertIn('"ok": false', output)
        self.assertIn("native_background_service_install_failed", output)

    def test_portable_fallback_without_native_attempt_remains_valid(self):
        rc, output = self._run(result={"installed": 1, "mode": "fallback-manifest"})
        self.assertEqual(rc, 0)
        self.assertIn('"ok": true', output)

    def test_core_systemd_install_requires_persistent_supervisor_active(self):
        with patch.object(install_services, "_systemd_active", return_value=False) as active:
            rc, output = self._run(result={"installed": 1, "mode": "systemd"}, env={"AGENT_MODE": "CORE"})
        self.assertEqual(rc, 2)
        self.assertIn("core_supervisor_service_not_active", output)
        active.assert_called_once_with("agentos-core-supervisor.service")

    def test_enabled_worker_host_must_also_be_active(self):
        with patch.object(install_services, "_systemd_active", side_effect=[True, False]) as active:
            rc, output = self._run(
                result={"installed": 1, "mode": "systemd"},
                env={
                    "AGENT_MODE": "CORE",
                    "AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE": "1",
                },
            )
        self.assertEqual(rc, 2)
        self.assertIn("employee_worker_host_service_not_active", output)
        self.assertEqual(
            [call.args[0] for call in active.call_args_list],
            ["agentos-core-supervisor.service", "agentos-employee-worker-host.service"],
        )

    def test_disabled_worker_host_is_not_required(self):
        with patch.object(install_services, "_systemd_active", return_value=True) as active:
            rc, output = self._run(
                result={"installed": 1, "mode": "systemd"},
                env={
                    "AGENT_MODE": "CORE",
                    "AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE": "0",
                },
            )
        self.assertEqual(rc, 0)
        self.assertIn('"ok": true', output)
        active.assert_called_once_with("agentos-core-supervisor.service")


if __name__ == "__main__":
    unittest.main()
