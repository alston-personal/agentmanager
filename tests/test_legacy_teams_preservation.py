"""Core install must never replace an external legacy Teams unit with a dead script."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
INSTALLER=ROOT/"scripts"/"install_systemd_user.sh"
RELEASE_SCRIPT=ROOT/"scripts"/"teams_bridge.py"
BUNDLE=ROOT/".github"/"workflows"/"oracle-core-bundle-immutable-runtime-convergence.yml"

class LegacyTeamsPreservationTests(unittest.TestCase):
    def test_absent_teams_provider_must_not_be_registered_or_restarted(self):
        if not RELEASE_SCRIPT.exists():
            content=INSTALLER.read_text(encoding="utf-8")
            self.assertNotIn('cat > "$USER_SYSTEMD_DIR/teams-commander.service"',content)
            self.assertNotIn("systemctl --user restart teams-commander.service",content)
            self.assertNotIn("agent-maintenance.timer teams-commander.service",content)
            self.assertIn("legacy Teams bridge",content)
        else:
            import py_compile
            py_compile.compile(str(RELEASE_SCRIPT), doraise=True)

    def test_old_active_service_remains_a_rollout_safety_fence(self):
        content=BUNDLE.read_text(encoding="utf-8")
        self.assertIn("teams-commander.service",content)
        self.assertIn('done < "$BACKUP/active-services"',content)
        self.assertIn('core_bundle_rollback=START',content)
        self.assertIn('core_bundle_preserved_active=$unit',content)

if __name__=="__main__":
    unittest.main()
