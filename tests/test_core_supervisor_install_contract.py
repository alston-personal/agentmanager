from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_systemd_user.sh"
SERVICE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.service"
ENV_EXAMPLE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.env.example"
ROOT_ENV_EXAMPLE = ROOT / ".env.example"
DELIVERY_DROPIN = ROOT / ".agent" / "scripts" / "agentos-core-supervisor-delivery.conf.example"
DOC = ROOT / "docs" / "CORE_SUPERVISOR_INSTALL.md"


class CoreSupervisorInstallContractTests(unittest.TestCase):
    def test_supervisor_asset_is_user_service_compatible(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertNotRegex(text, re.compile(r"^User=", re.MULTILINE))
        self.assertIn("WantedBy=default.target", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("NoNewPrivileges=true", text)

    def test_installer_materializes_s3_supervisor_on_core(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("agentos-core-supervisor.service", text)
        self.assertIn("core-supervisor.env", text)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled", text)
        self.assertIn("systemctl --user enable agentos-core-supervisor.service", text)
        self.assertIn("systemctl --user restart agentos-core-supervisor.service", text)
        self.assertIn('if [ ! -f "$SUPERVISOR_ENV_FILE" ]', text)

    def test_one_direct_install_requires_explicit_gate_and_existing_one(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT", text)
        self.assertIn("agentos-core-supervisor-delivery.conf", text)
        self.assertIn("realm/fabric.json", text)
        self.assertIn("realm/nodes.json", text)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct", text)
        self.assertIn("AGENTOS_SUPERVISOR_ONE_DATA_ROOT=", text)
        self.assertNotIn("github_actions", text.casefold())

    def test_installer_preserves_existing_host_local_supervisor_env(self):
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('if [ ! -f "$SUPERVISOR_ENV_FILE" ]', text)
        self.assertNotIn('cp "$LOGIC_ROOT/.agent/scripts/agentos-core-supervisor.env.example" "$SUPERVISOR_ENV_FILE"', text)

    def test_repository_env_defaults_s4_install_gate_closed(self):
        text = ROOT_ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            re.compile(r"^AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=0$", re.MULTILINE),
        )

    def test_deployment_doc_keeps_source_install_and_live_acceptance_separate(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("systemctl --user", text)
        self.assertIn("AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1", text)
        self.assertIn("does **not** initialize a Realm", text)
        self.assertIn("Repository merge != installer execution != Oracle deployment != operating acceptance", text)
        self.assertIn("CORE_SUPERVISOR_PERSISTENT_RECONCILIATION=VERIFIED", text)

    def test_source_assets_remain_secret_free(self):
        combined = "\n".join(
            p.read_text(encoding="utf-8") for p in (SERVICE, ENV_EXAMPLE, DELIVERY_DROPIN)
        ).casefold()
        for forbidden in ("password=", "token=", "secret=", "authorization=", "bearer "):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
