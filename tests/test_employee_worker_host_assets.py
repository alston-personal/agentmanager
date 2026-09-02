from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / ".agent" / "scripts" / "agentos-employee-worker-host.service"
ENV_EXAMPLE = ROOT / ".agent" / "scripts" / "agentos-employee-worker-host.env.example"
INSTALLER = ROOT / "scripts" / "install_systemd_user.sh"
REGISTRY = ROOT / "governance" / "employee-worker-adapters.json"


class EmployeeWorkerHostAssetTests(unittest.TestCase):
    def test_service_is_shared_user_service_with_no_network(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"^User=", re.MULTILINE))
        self.assertIn("WantedBy=default.target", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("employee_worker_host_daemon", text)
        self.assertNotIn("spec_steward_worker_cli", text)

    def test_service_has_read_only_wake_and_bounded_write_roots(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("ReadOnlyPaths=/home/ubuntu/agent-data/employee-wake-inbox", text)
        self.assertIn("/home/ubuntu/agent-data/employee-runtime", text)
        self.assertIn("/home/ubuntu/agent-data/employee-worker-host", text)
        self.assertIn("/home/ubuntu/agent-data/employee-worker-state", text)

    def test_installer_requires_separate_explicit_activation_gate(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE", text)
        self.assertIn("AGENTOS_EMPLOYEE_WAKE_ROOT is required", text)
        self.assertIn("configured wake root does not already exist", text)
        self.assertIn("AGENTOS_EMPLOYEE_WORKER_NODE_ID is required", text)
        self.assertIn("systemctl --user enable agentos-employee-worker-host.service", text)
        self.assertIn("systemctl --user restart agentos-employee-worker-host.service", text)
        self.assertNotIn('mkdir -p "$EMPLOYEE_WORKER_WAKE_ROOT"', text)

    def test_registry_and_assets_are_secret_free(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in (SERVICE, ENV_EXAMPLE, REGISTRY)
        ).casefold()
        for forbidden in ("password=", "token=", "secret=", "authorization=", "bearer "):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
