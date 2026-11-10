from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
FLOW=(ROOT/".github"/"workflows"/"oracle-core-bundle-immutable-runtime-convergence.yml").read_text(encoding="utf-8")

class TelegramImmutableServiceFenceTest(unittest.TestCase):
    def test_nonsecret_diagnostic_preserves_deploy_failure(self):
        self.assertIn('if [ "$unit" = "tg-commander.service" ]; then',FLOW)
        self.assertIn('tg_commander_liveness=',FLOW)
        self.assertIn('tg_commander_recent_exception_class=',FLOW)
        self.assertIn('core_bundle_rollback=START',FLOW)
        self.assertIn('exit 20',FLOW)
        self.assertNotIn('cat "$tg_log"',FLOW)

if __name__=="__main__":
    unittest.main()
