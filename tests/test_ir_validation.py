from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_core.ir_validation import validate_ir_change
from agent_core.project_continuation_index import publish_project_continuation
from scripts.documentation_reality_guard import IR_VALIDATION_CONTRACT, verify_file_set_coupling

ROOT = Path(__file__).resolve().parents[1]
PARENT = {"schema_version": "agentos.ir/v1", "index_id": "idx-1", "ir_id": "ir-1",
          "parent_ir_id": None, "goal": "Preserve useful work", "capability": "agentos.one.resolve",
          "constraints": [], "decisions": ["Retain reasons"], "pending_tasks": ["Verify gate"],
          "frontier": {"active_question": "Does loss get rejected?"},
          "continuation": {"next_action": "Verify gate"}}


def child():
    value = deepcopy(PARENT)
    value.update(index_id="idx-2", ir_id="ir-2", parent_ir_id="ir-1")
    return value


def envelope(ir, writer="explicit"):
    return {"project_id": "agentos-core", "execution_head": {
        "schema": "agentos.execution-head/v1", "index_id": ir["index_id"],
        "execution_head": {"updated_by": writer}},
        "continuation": {"index_id": ir["index_id"], "canonical_ir": ir}}


class IrValidationTests(unittest.TestCase):
    def test_receipt_binds_content_and_does_not_claim_semantic_review(self):
        receipt = validate_ir_change(child(), parent=PARENT)
        self.assertEqual(receipt["verdict"], "PASS")
        self.assertEqual(receipt["semantic_relevance"], "NOT_EVALUATED")
        changed = child()
        changed["goal"] = "New explicitly supplied goal"
        self.assertNotEqual(receipt["candidate_sha256"], validate_ir_change(changed, parent=PARENT)["candidate_sha256"])

    def test_loss_bad_shape_and_stale_generation_fail(self):
        for mutate in (lambda x: x.pop("frontier"),
                       lambda x: x.update(pending_tasks=[{"id": "T1"}]),
                       lambda x: x.update(ir_id="ir-1"),
                       lambda x: x.update(parent_ir_id="wrong")):
            value = child()
            mutate(value)
            with self.assertRaises(ValueError):
                validate_ir_change(value, parent=PARENT)

    def test_automatic_stop_cannot_promote_probe_into_next_action(self):
        value = child()
        value["continuation"]["next_action"] = "47 + 53 = 100; continue pending tasks"
        with self.assertRaisesRegex(ValueError, "AUTOMATIC_SEMANTIC_CHANGE"):
            validate_ir_change(value, parent=PARENT, writer="ir_stop_sync")
        value = child()
        value["evidence"] = [{"kind": "turn-checkpoint", "verdict": "RECORDED", "summary": "Probe output"}]
        self.assertEqual(validate_ir_change(value, parent=PARENT, writer="ir_stop_sync")["verdict"], "PASS")
        with self.assertRaisesRegex(ValueError, "AUTOMATIC_BOOTSTRAP"):
            validate_ir_change(PARENT, writer="ir_stop_sync")

    def test_direct_publisher_cannot_skip_validation_and_failure_preserves_files(self):
        project = {"id": "agentos-core", "identity_source": "governance-directory",
                   "integrity": {"mutation_allowed": True}}
        with tempfile.TemporaryDirectory() as temp, patch(
                "agent_core.project_continuation_index.resolve_project_identity", return_value=project):
            root = Path(temp)
            path = root / "projects/agentos-core"
            path.mkdir(parents=True)
            publish_project_continuation(envelope(deepcopy(PARENT)), data_root=root)
            files = [path / "execution-head.json", path / "continuity/latest.json"]
            original = [p.read_bytes() for p in files]
            value = child()
            value["continuation"]["next_action"] = "47 + 53 = 100"
            with self.assertRaisesRegex(ValueError, "IR_VALIDATION_FAILED"):
                publish_project_continuation(envelope(value, "ir_stop_sync"), data_root=root,
                                             expected_index_id="idx-1", expected_ir_id="ir-1")
            self.assertEqual([p.read_bytes() for p in files], original)
            result = publish_project_continuation(envelope(child()), data_root=root,
                                                  expected_index_id="idx-1", expected_ir_id="ir-1")
            self.assertEqual(result["validation"]["verdict"], "PASS")

    def test_cli_nonzero_on_failure_and_contract_changes_require_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "candidate.json"
            candidate.write_text(json.dumps(PARENT))
            command = [sys.executable, str(ROOT / "scripts/validate_canonical_ir.py"), str(candidate)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            candidate.write_text('{}')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        for missing in IR_VALIDATION_CONTRACT:
            errors = verify_file_set_coupling((IR_VALIDATION_CONTRACT - {missing}) | {"docs/CURRENT_STATE.md"}, "test")
            self.assertTrue(errors, missing)
        self.assertEqual(verify_file_set_coupling(IR_VALIDATION_CONTRACT | {"docs/CURRENT_STATE.md"}, "test"), [])
