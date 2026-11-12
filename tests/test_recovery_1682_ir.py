from __future__ import annotations

import importlib.util
import json
import io
import contextlib
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

    def test_apply_requires_postpublish_readback_and_reports_selector_drift(self):
        from agent_core.canonical_ir_handoff import advance_canonical_ir
        from agent_core.resolve_facade import resolve_continuation
        from agent_core.active_continuation import read_active_continuation
        argv = [
            "publish_recovery_1682_ir.py",
            "--expected-index-id", "idx-existing",
            "--expected-ir-id", "ir-existing",
            "--new-index-id", "idx-new",
            "--new-ir-id", "ir-new",
            "--apply",
        ]
        verified = {
            "execution_head": {"index_id": "idx-new"},
            "continuation": {"canonical_ir": {
                "index_id": "idx-new", "ir_id": "ir-new",
                "parent_ir_id": "ir-existing",
            }},
        }
        with patch.object(sys, "argv", argv), \
             patch("agent_core.canonical_ir_handoff.advance_canonical_ir",
                   return_value={"ok": True, "publish_receipt": {"ok": True}}) as publisher, \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=verified), \
             patch("agent_core.active_continuation.read_active_continuation",
                   return_value={
                       "project_id": "agentos-core", "index_id": "idx-existing",
                       "ir_id": "ir-existing",
                   }):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                module.main()
        result = json.loads(buf.getvalue())
        self.assertTrue(publisher.call_args.args[0]["execution_metadata"]["ir_published"])
        self.assertFalse(publisher.call_args.args[0]["execution_metadata"]["runtime_accepted"])
        self.assertTrue(result["canonical_ir_readback_verified"])
        self.assertFalse(result["active_selector_matches_new_ir"])
        self.assertTrue(result["active_selector_requires_reconciliation"])
        self.assertFalse(result["runtime_accepted"])

        with patch.object(sys, "argv", argv), \
             patch("agent_core.canonical_ir_handoff.advance_canonical_ir",
                   return_value={"ok": True, "publish_receipt": {"ok": True}}), \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value={"execution_head":{"index_id":"idx-existing"},
                                 "continuation":{"canonical_ir":{"ir_id":"ir-existing"}}}):
            with self.assertRaisesRegex(RuntimeError, "readback_mismatch"):
                module.main()

    def test_from_current_reads_real_generation_without_user_ids(self):
        argv = ["publish_recovery_1682_ir.py", "--from-current"]
        current = {
            "execution_head": {
                "schema": "agentos.execution-head/v1", "index_id": "idx-real"
            },
            "continuation": {"canonical_ir": {
                "schema_version": "agentos.ir/v1",
                "index_id": "idx-real", "ir_id": "ir-real",
            }},
        }
        with patch.object(sys, "argv", argv), \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=current):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                module.main()
        report = json.loads(buf.getvalue())
        req = report["request"]
        self.assertEqual(report["status"], "PREPARED_NOT_PUBLISHED")
        self.assertEqual(req["expected_index_id"], "idx-real")
        self.assertEqual(req["expected_ir_id"], "ir-real")
        self.assertTrue(req["new_ir_id"].startswith("ir-core-1682-"))
        self.assertNotEqual(req["new_ir_id"], "ir-real")

    def test_from_current_refuses_second_ir_after_prior_publish(self):
        argv = ["publish_recovery_1682_ir.py", "--from-current", "--apply"]
        already = self._published_ir(parent="ir-previous", index="idx-1682",
                                     ir_id="ir-1682")
        with patch.object(sys, "argv", argv), \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=already), \
             patch("agent_core.canonical_ir_handoff.advance_canonical_ir") as publish:
            with self.assertRaisesRegex(ValueError, "already_published_use_resume"):
                module.main()
            publish.assert_not_called()

    def test_from_current_malformed_generation_fails_closed(self):
        argv = ["publish_recovery_1682_ir.py", "--from-current"]
        bad = {
            "execution_head": {
                "schema": "agentos.execution-head/v1", "index_id": "idx-real"
            },
            "continuation": {"canonical_ir": {
                "schema_version": "agentos.ir/v1",
                "index_id": "idx-other", "ir_id": "ir-real",
            }},
        }
        with patch.object(sys, "argv", argv), \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=bad):
            with self.assertRaisesRegex(ValueError, "current_one_ir_generation_unresolved"):
                module.main()

    def test_sync_selector_refuses_other_project_after_ir_publish(self):
        argv = [
            "publish_recovery_1682_ir.py",
            "--expected-index-id", "idx-existing",
            "--expected-ir-id", "ir-existing",
            "--new-index-id", "idx-new",
            "--new-ir-id", "ir-new",
            "--apply", "--sync-active-selector",
        ]
        verified = {
            "execution_head": {"index_id": "idx-new"},
            "continuation": {"canonical_ir": {
                "index_id": "idx-new", "ir_id": "ir-new",
                "parent_ir_id": "ir-existing",
            }},
        }
        with patch.object(sys, "argv", argv), \
             patch("agent_core.canonical_ir_handoff.advance_canonical_ir",
                   return_value={"ok": True, "publish_receipt": {"ok": True}}), \
             patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=verified), \
             patch("agent_core.active_continuation.read_active_continuation",
                   return_value={"project_id": "other-project",
                                 "index_id": "idx-other", "ir_id": "ir-other"}):
            with self.assertRaisesRegex(RuntimeError, "no_implicit_takeover"):
                module.main()

    def _published_ir(self, *, parent="ir-parent", index="idx-new", ir_id="ir-new"):
        return {
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": index,
                "execution_head": {
                    "source": "recovery_1682_handoff_proposal",
                    "ir_published": True,
                    "runtime_accepted": False,
                    "recovery_live_receipt": False,
                },
            },
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": index,
                    "ir_id": ir_id,
                    "parent_ir_id": parent,
                    "goal": self.proposal["goal"],
                },
            },
        }

    def test_resume_selector_without_second_ir_publish(self):
        prior = {
            "project_id": "agentos-core", "index_id": "idx-parent",
            "ir_id": "ir-parent",
        }
        updated = {
            "project_id": "agentos-core", "index_id": "idx-new",
            "ir_id": "ir-new",
        }
        with patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=self._published_ir()), \
             patch("agent_core.active_continuation.read_active_continuation",
                   side_effect=[prior, updated]) as read_pointer, \
             patch("agent_core.active_continuation.activate_continuation") as activate, \
             patch("agent_core.canonical_ir_handoff.advance_canonical_ir") as publish:
            result = module.resume_selector_only(proposal=self.proposal)
        self.assertEqual(result["status"], "SELECTOR_RESUMED")
        self.assertTrue(result["selector_readback_verified"])
        self.assertFalse(result["new_ir_published"])
        self.assertEqual(read_pointer.call_count, 2)
        self.assertEqual(activate.call_args.kwargs["expected_previous"],
                         ("agentos-core", "idx-parent", "ir-parent"))
        publish.assert_not_called()

    def test_resume_is_idempotent_if_selector_already_current(self):
        current = {
            "project_id": "agentos-core", "index_id": "idx-new",
            "ir_id": "ir-new",
        }
        with patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=self._published_ir()), \
             patch("agent_core.active_continuation.read_active_continuation",
                   return_value=current), \
             patch("agent_core.active_continuation.activate_continuation") as activate:
            result = module.resume_selector_only(proposal=self.proposal)
        self.assertEqual(result["status"], "ALREADY_CURRENT")
        activate.assert_not_called()

    def test_resume_rejects_other_project_stale_generation_and_fake_authority(self):
        cases = [
            (self._published_ir(), {
                "project_id": "another-project", "index_id": "idx-other",
                "ir_id": "ir-other",
            }, "owned_by_another_project"),
            (self._published_ir(), {
                "project_id": "agentos-core", "index_id": "idx-old",
                "ir_id": "ir-unrelated",
            }, "does_not_match_published_parent"),
            ({**self._published_ir(), "execution_head": {
                "schema": "agentos.execution-head/v1", "index_id": "idx-new",
                "execution_head": {
                    "source": "fake",
                    "ir_published": True,
                    "runtime_accepted": False,
                    "recovery_live_receipt": False,
                },
            }}, {
                "project_id": "agentos-core", "index_id": "idx-parent",
                "ir_id": "ir-parent",
            }, "published_ir_not_proven"),
        ]
        for canonical, selected, expected in cases:
            with self.subTest(expected=expected), \
                 patch("agent_core.resolve_facade.resolve_continuation",
                       return_value=canonical), \
                 patch("agent_core.active_continuation.read_active_continuation",
                       return_value=selected), \
                 patch("agent_core.active_continuation.activate_continuation") as activate:
                with self.assertRaisesRegex(ValueError, expected):
                    module.resume_selector_only(proposal=self.proposal)
                activate.assert_not_called()

    def test_resume_rejects_missing_selector_and_concurrent_switch(self):
        prior = {
            "project_id": "agentos-core", "index_id": "idx-parent",
            "ir_id": "ir-parent",
        }
        with patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=self._published_ir()), \
             patch("agent_core.active_continuation.read_active_continuation",
                   side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "missing_active_selector"):
                module.resume_selector_only(proposal=self.proposal)
        with patch("agent_core.resolve_facade.resolve_continuation",
                   return_value=self._published_ir()), \
             patch("agent_core.active_continuation.read_active_continuation",
                   return_value=prior), \
             patch("agent_core.active_continuation.activate_continuation",
                   side_effect=ValueError("active_continuation_selector_cas_conflict")):
            with self.assertRaisesRegex(ValueError, "selector_cas_conflict"):
                module.resume_selector_only(proposal=self.proposal)

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
