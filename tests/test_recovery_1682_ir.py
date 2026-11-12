from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/publish_recovery_1682_ir.py"
PROPOSAL = ROOT / "docs/recovery-1682-canonical-ir-proposal.json"
spec = importlib.util.spec_from_file_location("publish_recovery_1682_ir", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecoveryCanonicalIRTests(unittest.TestCase):
    def setUp(self):
        self.proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))

    def prepare(self):
        return module.prepare(
            self.proposal,
            expected_index_id="idx-existing", expected_ir_id="ir-existing",
            new_index_id="idx-new", new_ir_id="ir-new",
        )

    def test_pending_work_and_evidence_are_preserved(self):
        request = self.prepare()
        self.assertEqual(request["project_id"], "agentos-core")
        self.assertEqual(request["execution_status"], "in_progress")
        self.assertTrue(request["pending_tasks"])
        self.assertTrue(request["decisions_append"])
        self.assertTrue(request["evidence"])
        self.assertFalse(request["execution_metadata"]["runtime_accepted"])
        self.assertFalse(request["execution_metadata"]["recovery_live_receipt"])
        self.assertFalse(request["execution_metadata"]["ir_published"])
        self.assertIn("#2271", json.dumps(request, ensure_ascii=False))

    def test_missing_or_stale_ids_not_forged(self):
        with self.assertRaises(ValueError):
            module.prepare(self.proposal, expected_index_id="",
                           expected_ir_id="x", new_index_id="new", new_ir_id="new-ir")
        with self.assertRaises(ValueError):
            module.prepare(self.proposal, expected_index_id="same",
                           expected_ir_id="old", new_index_id="same", new_ir_id="new")
        invalid = {**self.proposal, "ir_published": True}
        with self.assertRaises(ValueError):
            module.prepare(invalid, expected_index_id="old",
                           expected_ir_id="old", new_index_id="new", new_ir_id="new")

    def test_no_shadow_publisher_or_authority_bypass(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("advance_canonical_ir(", src)
        self.assertNotIn("publish_project_continuation(", src)
        self.assertNotIn("os.replace(", src)
        self.assertNotIn("force=True", src)
        self.assertNotIn("new_ir_id = uuid", src)
        self.assertIn("PREPARED_NOT_PUBLISHED", src)

    def test_cli_dry_run_never_publishes(self):
        cmd = [
            sys.executable, str(SCRIPT),
            "--expected-index-id", "idx-existing",
            "--expected-ir-id", "ir-existing",
            "--new-index-id", "idx-new",
            "--new-ir-id", "ir-new",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                check=True, timeout=10)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PREPARED_NOT_PUBLISHED")
        self.assertEqual(payload["request"]["expected_index_id"], "idx-existing")
        self.assertEqual(payload["request"]["new_ir_id"], "ir-new")
        self.assertNotIn("publish_receipt", payload)


if __name__ == "__main__":
    unittest.main()
