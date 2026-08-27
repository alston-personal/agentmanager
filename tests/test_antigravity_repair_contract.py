import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'repair_antigravity_relay_user.sh'
ACTION_INSTALLER = ROOT / 'scripts' / 'install_action_relay_user.sh'


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


class AntigravityRepairContractTests(unittest.TestCase):
    def test_repair_is_branch_aware_and_allowlisted(self):
        text = _text(SCRIPT)
        self.assertIn('SOURCE_REF="${AGENTOS_REF:-main}"', text)
        self.assertIn('main|feature/realm-node-fabric-readiness', text)
        self.assertIn('git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"', text)
        self.assertIn('SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)', text)
        self.assertNotIn('origin/main:', text)

    def test_repair_materializes_join_bootstrap_generation(self):
        text = _text(SCRIPT)
        self.assertIn('show_source agent_core/node_bootstrap.py', text)
        self.assertIn('install -m 0664 "$TMPDIR/node_bootstrap.py" "$REALM_RUNTIME/agent_core/node_bootstrap.py"', text)
        self.assertIn('realm_fabric_bootstrap_route=PASS', text)
        self.assertIn('realm_fabric_benchmark_route=PASS', text)

    def test_relay_boundary_uses_authorized_agentos_group_before_worker_start(self):
        text = _text(SCRIPT)
        self.assertIn("ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker", text)
        unit_section = text.split('cat > "$UNIT" <<EOF', 1)[1].split('EOF', 1)[0]
        self.assertNotIn('NoNewPrivileges=true', unit_section)
        self.assertIn('UMask=0007', unit_section)

    def test_action_relay_installer_preserves_correct_foreign_owned_shared_boundary(self):
        text = _text(ACTION_INSTALLER)
        self.assertIn('ensure_shared_dir()', text)
        self.assertIn("group=$(stat -c '%G' \"$path\")", text)
        self.assertIn("owner=$(stat -c '%U' \"$path\")", text)
        self.assertIn('if [ "$group" != agentos ]; then', text)
        self.assertIn('if [ "$owner" != ubuntu ]; then', text)
        self.assertIn('ubuntu cannot repair foreign-owned shared boundary', text)
        self.assertNotIn('chgrp agentos "$RELAY_ROOT" "$RELAY_ROOT/inbox"', text)
        self.assertNotIn('chmod 2770 "$RELAY_ROOT" "$RELAY_ROOT/inbox"', text)


if __name__ == '__main__':
    unittest.main()
