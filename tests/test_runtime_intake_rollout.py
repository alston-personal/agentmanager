"""Guard that the existing Oracle immutable Core rollout sees intake changes."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml"

class RuntimeIntakeRolloutTest(unittest.TestCase):
    def test_immutable_core_bundle_tracks_approved_intake_source(self):
        content=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("push:",content)
        self.assertIn("branches: [core/integration]",content)
        for entry in ("scripts/issue_work_intake.py","scripts/work_completion.py","tests/test_issue_work_intake.py"):
            self.assertIn("'"+entry+"'",content)
        self.assertIn("SOURCE_COMMIT=\"$1\"",content)
        self.assertIn('ln -sfn "$RELEASE" "$CURRENT"',content)
        self.assertIn("core_bundle_immutable_runtime=PASS",content)

if __name__=="__main__":unittest.main()
