from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_realm_fabric_user.sh"


class RealmFabricInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = INSTALLER.read_text(encoding="utf-8")

    def test_existing_durable_realm_identity_is_preserved(self):
        self.assertIn('FABRIC_FILE="$DATA_ROOT/realm/fabric.json"', self.text)
        self.assertIn('REQUESTED_REALM_ID="${AGENTOS_REALM_ID:-}"', self.text)
        self.assertIn('if [ -f "$FABRIC_FILE" ]; then', self.text)
        self.assertIn('REALM_ID="$EXISTING_REALM_ID"', self.text)
        self.assertIn('REALM_ID="${REQUESTED_REALM_ID:-realm-primary}"', self.text)

    def test_explicit_conflicting_realm_identity_fails_closed(self):
        self.assertIn(
            'if [ -n "$REQUESTED_REALM_ID" ] && [ "$REQUESTED_REALM_ID" != "$EXISTING_REALM_ID" ]; then',
            self.text,
        )
        self.assertIn('exit 4', self.text)
        self.assertNotIn('REALM_ID="${AGENTOS_REALM_ID:-realm-primary}"', self.text)

    def test_installer_requires_and_enters_agentos_group_boundary(self):
        self.assertIn('command -v sg >/dev/null 2>&1', self.text)
        self.assertIn('getent group agentos >/dev/null', self.text)
        self.assertIn("grep -qx agentos", self.text)
        self.assertIn('Environment=PYTHONPATH=$LOGIC_ROOT', self.text)
        self.assertIn(
            "ExecStart=/usr/bin/sg agentos -c '$PYTHON_BIN -m agent_core.realm_cli serve --host 127.0.0.1 --port $PORT'",
            self.text,
        )
        self.assertIn('realm_group_boundary=agentos', self.text)

    def test_installer_restarts_existing_service_after_unit_update(self):
        daemon_reload = self.text.index('systemctl --user daemon-reload')
        enable = self.text.index('systemctl --user enable agentos-realm-fabric.service')
        restart = self.text.index('systemctl --user restart agentos-realm-fabric.service')
        active = self.text.index('systemctl --user is-active --quiet agentos-realm-fabric.service')
        self.assertLess(daemon_reload, enable)
        self.assertLess(enable, restart)
        self.assertLess(restart, active)
        self.assertNotIn('enable --now agentos-realm-fabric.service', self.text)

    def test_restarted_service_uses_bounded_health_readiness_window(self):
        self.assertIn('realm_ready=0', self.text)
        self.assertIn('for _ in $(seq 1 10); do', self.text)
        self.assertIn('curl -fsS --max-time 2 "http://127.0.0.1:$PORT/v1/health"', self.text)
        self.assertIn('sleep 1', self.text)
        self.assertIn('if [ "$realm_ready" -ne 1 ]; then', self.text)
        self.assertIn('Realm Fabric did not become healthy after restart', self.text)
        self.assertIn('exit 4', self.text)


if __name__ == "__main__":
    unittest.main()
