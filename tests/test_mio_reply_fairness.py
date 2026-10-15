"""Regression tests for Mio reply fairness and persistent parent reservation."""
import ast
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

def isolated_function(filename, function_name, namespace):
    source = ast.parse((SCRIPTS / filename).read_text(encoding="utf-8"))
    node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    code = compile(ast.Module(body=[node], type_ignores=[]), str(SCRIPTS / filename), "exec")
    exec(code, namespace)
    return namespace[function_name]

class ReplySafetyTests(unittest.TestCase):
    def test_oldest_overdue_reply_preempts_fresh_observation(self):
        now = datetime.now(timezone.utc)
        fn = isolated_function("persona_social_executor.py", "select_action", {
            "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
            "image_journal_path": lambda _: Path("/nonexistent-mio-media-journal")
        })
        observation = {"capability": "social.threads.observe", "status": "candidate"}
        newer = {"capability": "social.reply.send", "status": "candidate",
                 "not_before": (now-timedelta(minutes=95)).isoformat()}
        older = {"capability": "social.reply.send", "status": "candidate",
                 "not_before": (now-timedelta(hours=3)).isoformat()}
        self.assertIs(fn([observation, newer, older]), older)

    def test_recent_reply_yields_to_observation(self):
        fn = isolated_function("persona_social_executor.py", "select_action", {
            "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
            "image_journal_path": lambda _: Path("/nonexistent-mio-media-journal")
        })
        observe = {"capability": "social.threads.observe"}
        reply = {"capability": "social.reply.send",
                 "not_before": (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()}
        self.assertIs(fn([reply, observe]), observe)

    def test_readback_reconciles_unique_exact_parent_without_writing(self):
        fn = isolated_function("persona_social_executor.py", "reconcile_held_reply", {
            "read_items": lambda request, headers: ([{
                "id": "900", "is_reply_owned_by_me": True,
                "replied_to": {"id": "123"}, "text": "hello"
            }], {"ok": True}),
            "save": lambda path, obj: path.write_text(json.dumps(obj), encoding="utf-8")
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"pdca").mkdir()
            target = {"action_id": "reply-test", "reply_to_id": "123",
                      "root_post_id": "456", "primary_text": "hello",
                      "capability": "social.reply.send", "status": "in_progress"}
            state = {"pending_external_actions": [target]}
            result = fn(root, state, target, root/"pdca"/"receipt.json", {}, {}, "2026-10-15T00:00:00Z")
            self.assertEqual(result["readback_status"], "CONFIRMED")
            self.assertEqual(target["status"], "completed")
            self.assertFalse(result["write_performed"])

    def test_absent_readback_keeps_reconciliation_hold(self):
        fn = isolated_function("persona_social_executor.py", "reconcile_held_reply", {
            "read_items": lambda request, headers: ([], {"ok": True}),
            "save": lambda path, obj: path.write_text(json.dumps(obj), encoding="utf-8")
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"pdca").mkdir()
            target = {"action_id": "reply-test", "reply_to_id": "123",
                      "root_post_id": "456", "primary_text": "hello",
                      "capability": "social.reply.send", "status": "in_progress"}
            state = {"pending_external_actions": [target]}
            result = fn(root, state, target, root/"pdca"/"receipt.json", {}, {}, "2026-10-15T00:00:00Z")
            self.assertEqual(result["readback_status"], "NOT_OBSERVED")
            self.assertEqual(target["status"], "in_progress")
            self.assertTrue(target["reconciliation_required"])

    def test_reserved_parent_survives_pending_queue_loss(self):
        fn = isolated_function("persona_reply_intent_generator.py", "reserved_reply_parents", {
            "load": lambda p: json.loads(p.read_text(encoding="utf-8"))
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intents = root/"pdca"/"reply_intents"
            intents.mkdir(parents=True)
            (intents/"old.json").write_text(json.dumps({
                "capability": "social.reply.send", "reply_to_id": "123",
                "status": "candidate"
            }), encoding="utf-8")
            self.assertIn("123", fn(root, []))
            self.assertIn("456", fn(root, [{
                "capability": "social.reply.send", "reply_to_id": "456"
            }]))
            self.assertNotIn("789", fn(root, []))

if __name__ == "__main__":
    unittest.main()
