from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_systemd_user.sh"
SERVICE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.service"
ENV_EXAMPLE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.env.example"
DELIVERY_DROPIN = ROOT / ".agent" / "scripts" / "agentos-core-supervisor-delivery.conf.example"


class CoreSupervisorInstallContractTests(unittest.TestCase):
    def test_supervisor_asset_is_user_service_compatible(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"^User=", re.MULTILINE))
        self.assertIn("WantedBy=default.target", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("NoNewPrivileges=true", text)

    def test_installer_materializes_supervisor_with_disabled_delivery_by_default(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("agentos-core-supervisor.service", text)
        self.assertIn("core-supervisor.env", text)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled", text)
        self.assertIn("systemctl --user enable agentos-core-supervisor.service", text)
        self.assertIn("systemctl --user restart agentos-core-supervisor.service", text)
        self.assertNotIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct\n", text)

    def test_one_direct_install_requires_explicit_gate(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT", text)
        self.assertIn("agentos-core-supervisor-delivery.conf", text)
        self.assertIn("realm/fabric.json", text)
        self.assertIn("realm/nodes.json", text)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct", text)

    def test_source_assets_remain_secret_free(self):
        combined = "\n".join(
            p.read_text(encoding="utf-8") for p in (SERVICE, ENV_EXAMPLE, DELIVERY_DROPIN)
        ).casefold()
        for forbidden in ("password=", "token=", "secret=", "authorization=", "bearer "):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
