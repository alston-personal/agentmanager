"""Regression tests for bounded durable Mio reply reconciliation recovery."""
import ast
import json
import tempfile
import unittest
from pathlib import Path


def load_recovery():
    source = Path(__file__).resolve().parents[1] / "scripts/persona_social_executor.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "recover_orphan_reply_intent")
    namespace = {"json": json, "save": lambda p, obj: p.write_text(json.dumps(obj), encoding="utf-8")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["recover_orphan_reply_intent"]


class OrphanRecoveryBoundTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "pdca/reply_intents").mkdir(parents=True)
        self.recover = load_recovery()
        self.orphan = {
            "action_id": "reply-old", "capability": "social.reply.send",
            "status": "in_progress", "created_at": "2026-10-01T00:00:00Z",
            "reply_to_id": "123", "root_post_id": "456",
        }
        (self.root / "pdca/reply_intents/reply-old.json").write_text(json.dumps(self.orphan))

    def test_held_reply_blocks_new_orphan_without_mutation(self):
        held = {"action_id": "reply-held", "capability": "social.reply.send",
                "status": "in_progress", "reconciliation_required": True}
        state = {"pending_external_actions": [held]}
        self.assertIsNone(self.recover(self.root, state))
        self.assertEqual(state["pending_external_actions"], [held])
        self.assertEqual(json.loads((self.root / "pdca/reply_intents/reply-old.json").read_text()), self.orphan)

    def test_unrelated_pending_allows_one_read_only_restore(self):
        state = {"pending_external_actions": [{"action_id": "other", "capability": "social.threads.observe", "status": "candidate"}]}
        restored = self.recover(self.root, state)
        self.assertEqual(restored["action_id"], "reply-old")
        self.assertTrue(restored["reconciliation_required"])
        self.assertFalse(restored["write_replay_allowed"])
        self.assertEqual(len(state["pending_external_actions"]), 2)
        self.assertIsNone(self.recover(self.root, state))
        self.assertEqual(len(state["pending_external_actions"]), 2)


if __name__ == "__main__":
    unittest.main()
