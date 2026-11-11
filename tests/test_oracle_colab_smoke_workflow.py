"""Contract tests for the real, manually triggered Colab H3 smoke workflow.

Run entirely offline: never connect to Colab, create GPU sessions, or dispatch
GitHub workflows. Ensure source revisions do not reintroduce a two-hour
paid-compute timeout or accidentally trigger rendering during pull-request CI.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import textwrap
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/oracle-colab-minimax-h3-smoke.yml"


class H3SmokeWorkflowGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_only_manual_event_can_enter_billable_job(self):
        src = self.source
        self.assertIn("  workflow_dispatch:", src)
        self.assertIn("  pull_request:", src)
        self.assertRegex(src, r"(?m)^  smoke:\n    if: github\.event_name == 'workflow_dispatch'$")
        self.assertRegex(src, r"(?m)^  contract:\n    if: github\.event_name == 'pull_request'$")
        self.assertIn("python3 -m unittest discover -s tests -p test_oracle_colab_smoke_workflow.py -v", src)

    def test_bounded_timeout_and_no_retry(self):
        src = self.source
        self.assertIn("    timeout-minutes: 45", src)
        self.assertIn("            --timeout 1500 \\", src)
        self.assertIn("  cancel-in-progress: false", src)
        self.assertNotIn("--timeout 7200", src)
        self.assertNotIn("retry", src[src.index("            --timeout 1500"):src.index("          USAGE_AFTER=")])

    def test_usage_failure_blocks_paid_gpu(self):
        src = self.source
        self.assertIn('if [ "$USAGE_BEFORE_RC" -ne 0 ]; then', src)
        self.assertIn("            RC=23", src)
        self.assertRegex(src, r"(?s)if \[ \"\$USAGE_BEFORE_RC\" -ne 0 \]; then\s+RC=23\s+else\s+set \+e\s+python3 \"\$RELEASE/scripts/runner.py\" batch")

    def test_receipt_python_syntax_and_failure_class(self):
        src = self.source
        start = src.index('          python3 - "$EVIDENCE/h3-smoke-$RUN_ID.json"')
        start = src.index("<<'PY'\n", start) + len("<<'PY'\n")
        end = src.index("\n          PY", start)
        embedded = textwrap.dedent(src[start:end])
        ast.parse(embedded, filename="colab-smoke-embedded-receipt.py")
        self.assertIn("COLAB_KERNEL_CONNECTION_LOST", embedded)
        self.assertIn("COLAB_EXECUTION_TIMEOUT", embedded)
        self.assertIn("COLAB_USAGE_PREFLIGHT_FAILED", embedded)
        self.assertIn('"failure_class":failure_class', embedded)
        self.assertIn("outputs", embedded)


if __name__ == "__main__":
    unittest.main()
