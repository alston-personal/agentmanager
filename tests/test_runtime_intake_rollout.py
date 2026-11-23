"""Guard that the immutable Core intake stays packaged under a main-only release fence."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml"


class RuntimeIntakeRolloutTest(unittest.TestCase):
    def test_immutable_core_bundle_tracks_approved_intake_source(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        events = content.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("workflow_dispatch:", events)
        self.assertNotIn("\n  push:", events)
        self.assertIn("expected_main_sha:", events)
        self.assertIn("core_bundle_approved:", events)
        job = content.split("\n  converge:\n", 1)[1]
        self.assertIn("github.ref_name == 'main'", job)
        self.assertIn("inputs.core_bundle_approved == true", job)
        self.assertIn('test "${GITHUB_SHA}" = "${EXPECTED_MAIN_SHA}"', job)
        self.assertIn('test -f "$RELEASE/scripts/issue_work_intake.py"', content)
        self.assertIn('grep -Fq \'def eligible(\' "$RELEASE/scripts/issue_work_intake.py"', content)
        self.assertIn('SOURCE_COMMIT="$1"', content)
        self.assertIn('ln -sfn "$RELEASE" "$CURRENT"', content)
        self.assertIn("core_bundle_immutable_runtime=PASS", content)


if __name__ == "__main__":
    unittest.main()
