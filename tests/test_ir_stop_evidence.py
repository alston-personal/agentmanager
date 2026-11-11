from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_core.active_continuation import activate_continuation
from agent_core.ir_validation import SEMANTIC_FIELDS
from agent_core.project_continuation_index import publish_project_continuation
from agent_core.resolve_facade import resolve_continuation
from agentos_node.ir_stop_sync import advance_active_ir_checkpoint, handle_stop_payload
from tests.test_ir_validation import PARENT, envelope


class StopEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "projects/agentos-core").mkdir(parents=True)
        project = {"id": "agentos-core", "identity_source": "governance-directory",
                   "integrity": {"mutation_allowed": True}}
        for target in ("agent_core.project_continuation_index.resolve_project_identity",
                       "agent_core.resolve_facade.resolve_project_identity"):
            mock = patch(target, return_value=project)
            mock.start()
            self.addCleanup(mock.stop)
        value = deepcopy(PARENT)
        value["continuation"] = {"recommended_action": "Verify gate", "acceptance": "Review evidence"}
        self.initial = value
        publish_project_continuation(envelope(value), data_root=self.root)
        activate_continuation("agentos-core", index_id="idx-1", ir_id="ir-1", reason="test", data_root=self.root)

    def current(self):
        return resolve_continuation("agentos-core", data_root=self.root)["continuation"]["canonical_ir"]

    def checkpoint(self, **extra):
        return advance_active_ir_checkpoint(surface="test", model_name="test", user_intent="probe",
                                            assistant_summary="47 + 53 = 100", data_root=self.root, **extra)

    def test_stop_payload_records_probe_without_changing_task_semantics(self):
        transcript = self.root / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": "47 + 53 = 100"}}) + "\n")
        response = handle_stop_payload({"hook_event_name": "Stop", "session_id": "test",
                                        "transcript_path": str(transcript), "last_user_input": "arithmetic probe"},
                                       data_root=self.root)
        self.assertEqual(response, {})
        ir = self.current()
        self.assertNotEqual(ir["ir_id"], "ir-1")
        for field in SEMANTIC_FIELDS:
            self.assertEqual(ir.get(field), self.initial.get(field), field)
        self.assertIn("47 + 53", ir["evidence"][-1]["summary"])
        self.assertEqual(ir["evidence"][-1]["task_relevance"], "NOT_EVALUATED")
        audit = json.loads((self.root / "runtime/ir-stop-sync-last.json").read_text())
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["handoff"]["publish_receipt"]["validation"]["verdict"], "PASS")

    def test_explicit_changes_require_observed_generation_and_remain_supported(self):
        with self.assertRaisesRegex(ValueError, "observed"):
            self.checkpoint(explicit_next_action="Review test results")
        with self.assertRaisesRegex(ValueError, "automatic Stop"):
            self.checkpoint(automatic=True, explicit_next_action="Unrelated task")
        fence = dict(expected_project_id="agentos-core", expected_index_id="idx-1", expected_ir_id="ir-1")
        self.checkpoint(explicit_next_action="Review test results", explicit_decision="Evidence checked", **fence)
        ir = self.current()
        self.assertEqual(ir["continuation"]["next_action"], "Review test results")
        self.assertIn("Evidence checked", ir["decisions"])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.checkpoint(completed_tasks=["Verify gate"], **fence)

    def test_missing_selector_never_falls_back_to_core_or_mutates_ir(self):
        (self.root / "runtime/active-continuation.json").unlink()
        with self.assertRaises(Exception):
            self.checkpoint(automatic=True)
        self.assertEqual(self.current(), self.initial)

    def test_automatic_failure_is_audited_without_blocking_chat(self):
        before = self.current()
        with patch("agentos_node.ir_stop_sync.advance_active_ir_checkpoint", side_effect=ValueError("secret-value")):
            self.assertEqual(handle_stop_payload({"hook_event_name": "Stop", "last_user_input": "probe"},
                                                 data_root=self.root), {})
        audit = (self.root / "runtime/ir-stop-sync-last.json").read_text()
        self.assertNotIn("secret-value", audit)
        self.assertFalse(json.loads(audit)["ok"])
        self.assertEqual(self.current(), before)
