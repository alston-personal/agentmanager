import unittest
from scripts.check_branch_convergence_paths import classify, audit

class BranchConvergencePathRiskTest(unittest.TestCase):
    def test_core_requires_review(self):
        self.assertEqual(classify(".agent/CONSTITUTION.yaml"), "RED")
        self.assertEqual(classify(".github/workflows/deploy.yml"), "RED")
        self.assertEqual(classify("scripts/deploy_core.sh"), "RED")

    def test_content_continues(self):
        self.assertEqual(classify("stories/chapter.md"), "GREEN")

    def test_unknown_fails_closed(self):
        self.assertEqual(classify("unexpected/new-component.py"), "UNKNOWN")
        self.assertTrue(audit(["unexpected/new-component.py"])["requires_governed_review"])

    def test_traversal_invalid(self):
        self.assertEqual(classify("../secret"), "INVALID")

if __name__ == "__main__":
    unittest.main()
