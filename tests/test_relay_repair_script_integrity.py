"""Regression guard for protected-main Action Relay repair script.

Static/syntax checks only: never execute installers on CI.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_antigravity_relay_user.sh"


class RelayRepairSourceIntegrity(unittest.TestCase):
    def test_shell_parses_without_conflict_markers(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertFalse(any(line.startswith(("<<<<<<<", "=======", ">>>>>>>")) for line in script.splitlines()))
        completed = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_required_source_and_isolation_preflight_before_mutation(self):
        script = SCRIPT.read_text(encoding="utf-8")
        before_materialize = script.split('REPAIR_STAGE="materialize_source"', 1)[0]
        for name in (
            "ACTION_RUNTIME", "DATA_ROOT", "SOURCE_REF",
            "EXPECTED_SOURCE_COMMIT", "PROVIDER", "SPOOL", "UNIT_DIR",
            "UNIT", "MANIFEST", "CODEX_CONFIG", "TMPDIR",
        ):
            self.assertIn(name + "=", before_materialize)
        self.assertIn('AGENTOS_REF:-main', before_materialize)
        self.assertIn("AGENTOS_SOURCE_COMMIT", before_materialize)
        self.assertIn('trap cleanup EXIT', before_materialize)
        self.assertIn('merge-base --is-ancestor', script)
        self.assertIn('AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"', script)

    def test_repair_must_not_mutate_realm(self):
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("realm_fabric_deploy_authority_separation_v1", script)
        self.assertIn("realm_fabric_mutation=NONE", script)
        self.assertNotIn("systemctl --user restart agentos-realm-fabric.service", script)
        self.assertNotIn("agentos.realm-fabric.install_release", script)


if __name__ == "__main__":
    unittest.main()
