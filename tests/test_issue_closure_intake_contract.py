"""Contract tests for the existing Intake workflow's closure-audit extension."""
import subprocess
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/oracle-approved-issue-intake.yml"


class IssueClosureIntakeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_preserves_original_open_only_intake(self):
        self.assertIn("state=open&labels=agentos%3Aapproved", self.source)
        self.assertIn('approved-issues.json', self.source)

    def test_open_and_closed_snapshot_is_explicit_and_bounded(self):
        self.assertIn("state=all&labels=agentos%3Aapproved", self.source)
        self.assertIn("for page in range(1, 21)", self.source)
        self.assertIn("closure_snapshot_page_limit_exceeded", self.source)
        self.assertIn('if "pull_request" in item:', self.source)
        self.assertIn('result.append({"number":number,"state":state})', self.source)

    def test_uses_installed_runtime_checker_not_pr_artifact(self):
        self.assertIn('if test -f "$release/scripts/issue_completion_reconciliation.py"; then', self.source)
        self.assertIn('"$release/scripts/issue_completion_reconciliation.py"', self.source)
        self.assertIn("closure_audit_status=NOT_DEPLOYED", self.source)

    def test_anomaly_is_data_not_runtime_failure(self):
        self.assertIn('test "$audit_code" -ne 2', self.source)
        self.assertIn("closure_audit_unverified_closures=", self.source)
        self.assertNotIn("gh issue reopen", self.source)
        self.assertNotIn("agentos_advance_ir", self.source)

    def test_no_credentials_sent_in_snapshot(self):
        self.assertIn('result.append({"number":number,"state":state})', self.source)
        self.assertIn("issue-closure-states.json", self.source)
        self.assertNotIn('"$target:/home/ubuntu/agent-data/governance/issue-intake/gh-token"', self.source)

    def test_all_inline_shell_steps_parse(self):
        # Keep indentation semantics of GitHub Actions literal YAML run blocks.
        lines = self.source.splitlines()
        scripts = []
        for i, line in enumerate(lines):
            if line == "        run: |":
                block = []
                for row in lines[i + 1:]:
                    if row and not row.startswith("          "):
                        break
                    block.append(row[10:] if row else "")
                scripts.append("\n".join(block) + "\n")
        self.assertGreaterEqual(len(scripts), 2)
        for script in scripts:
            process = subprocess.run(["bash", "-n"], input=script, text=True,
                                     capture_output=True, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
