from pathlib import Path
import unittest
P=Path(__file__).resolve().parents[1]/".github"/"workflows"/"oracle-core-bundle-immutable-runtime-convergence.yml"
class EarlyTelegramProofTest(unittest.TestCase):
    def test_early_guard_outputs_bounded_class_and_still_rolls_back(self):
        source=P.read_text()
        self.assertIn('tg_commander_first_gate=',source)
        self.assertIn('tg_commander_first_gate_exception=',source)
        self.assertIn('exit 29',source)
        self.assertIn('core_bundle_rollback=START',source)
        self.assertNotIn('cat "$DATA_ROOT/logs/tg_bridge.log"',source)
if __name__=="__main__": unittest.main()
