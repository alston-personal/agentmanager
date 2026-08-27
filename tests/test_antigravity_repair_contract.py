import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'repair_antigravity_relay_user.sh'


def _text() -> str:
    return SCRIPT.read_text(encoding='utf-8')


class AntigravityRepairContractTests(unittest.TestCase):
    def test_repair_is_branch_aware_and_allowlisted(self):
        text = _text()
        self.assertIn('SOURCE_REF="${AGENTOS_REF:-main}"', text)
        self.assertIn('main|feature/realm-node-fabric-readiness', text)
        self.assertIn('git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"', text)
        self.assertIn('SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)', text)
        self.assertNotIn('origin/main:', text)

    def test_repair_materializes_join_bootstrap_generation(self):
        text = _text()
        self.assertIn('show_source agent_core/node_bootstrap.py', text)
        self.assertIn('install -m 0664 "$TMPDIR/node_bootstrap.py" "$REALM_RUNTIME/agent_core/node_bootstrap.py"', text)
        self.assertIn('realm_fabric_bootstrap_route=PASS', text)
        self.assertIn('realm_fabric_benchmark_route=PASS', text)

    def test_relay_boundary_uses_authorized_agentos_group_before_worker_start(self):
        text = _text()
        self.assertIn("ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker", text)
        unit_section = text.split('cat > "$UNIT" <<EOF', 1)[1].split('EOF', 1)[0]
        self.assertNotIn('NoNewPrivileges=true', unit_section)
        self.assertIn('UMask=0007', unit_section)


if __name__ == '__main__':
    unittest.main()
