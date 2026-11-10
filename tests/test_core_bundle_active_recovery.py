from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/".github"/"workflows"/"oracle-core-bundle-immutable-runtime-convergence.yml"
class PreexistingActiveServiceRecoveryTest(unittest.TestCase):
    def test_only_previously_active_services_get_single_restart_and_fail_closed(self):
        src=SCRIPT.read_text(encoding="utf-8")
        self.assertIn('done < "$BACKUP/active-services"',src)
        self.assertIn('if ! systemctl --user is-active --quiet "$unit"; then',src)
        self.assertIn('if ! systemctl --user restart "$unit"; then',src)
        self.assertIn('core_bundle_preserved_service_recover=$unit:RESTART_FAILED',src)
        self.assertIn('core_bundle_preserved_service_recover=$unit:NOT_ACTIVE',src)
        self.assertIn('core_bundle_rollback=START',src)
        self.assertIn('trap rollback EXIT',src)
if __name__=="__main__":unittest.main()
