import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.wow_slot_publisher import (
    SLOT_NAME, SlotPublishError, publish_companion_answer
)
from scripts.wow_companion_reply import SCHEMA


class CompanionPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / SLOT_NAME
        self.directory.mkdir()
        (self.directory / (SLOT_NAME + ".toc")).write_text(
            "## Interface: 16001\n## LoadOnDemand: 1\nReply.lua\n", encoding="utf-8"
        )
        self.target = self.directory / "Reply.lua"
        self.target.write_bytes(b"AgentOSWoWReplySlot = nil\n")
        self.reply = {
            "schema": SCHEMA, "request_id": "ask-77",
            "category": "general", "answer": "See the mage trainer.",
            "sources": [], "action": {"type": "ui.answer"}
        }

    def _publish(self, reply=None, directory=None, request_id="ask-77"):
        return publish_companion_answer(
            reply if reply is not None else self.reply,
            directory if directory is not None else self.directory,
            expected_request_id=request_id
        )

    def test_publishes_only_validated_answer_to_installed_slot(self):
        result = self._publish()
        self.assertEqual(result, {
            "status": "PUBLISHED", "request_id": "ask-77", "game_received": False
        })
        contents = self.target.read_bytes()
        self.assertIn(b"AgentOSWoWReplySlot = {", contents)
        self.assertNotIn(b"See the mage trainer.", contents)
        self.assertFalse(list(self.directory.glob("*.tmp")))

    def test_reject_mismatched_correlation_without_write(self):
        before = self.target.read_bytes()
        with self.assertRaisesRegex(SlotPublishError, "COMPANION_REPLY_REJECTED"):
            self._publish(request_id="ask-78")
        self.assertEqual(self.target.read_bytes(), before)

    def test_reject_wrong_directory_without_write(self):
        wrong_dir = Path(self.temp.name) / "UnexpectedAddon"
        wrong_dir.mkdir()
        with self.assertRaisesRegex(SlotPublishError, "INVALID_SLOT_DIRECTORY"):
            self._publish(directory=wrong_dir)
        self.assertEqual(self.target.read_bytes(), b"AgentOSWoWReplySlot = nil\n")

    def test_reject_target_symlink(self):
        self.target.unlink()
        outside = Path(self.temp.name) / "outside.lua"
        outside.write_bytes(b"secret")
        try:
            self.target.symlink_to(outside)
        except OSError:
            self.skipTest("symlink privileges unavailable on this platform")
        with self.assertRaisesRegex(SlotPublishError, "UNSAFE_SLOT_PATH"):
            self._publish()
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_reject_toc_symlink(self):
        toc = self.directory / (SLOT_NAME + ".toc")
        toc.unlink()
        outside = Path(self.temp.name) / "outside.toc"
        outside.write_bytes(b"## LoadOnDemand: 1\n")
        try:
            toc.symlink_to(outside)
        except OSError:
            self.skipTest("symlink privileges unavailable on this platform")
        with self.assertRaisesRegex(SlotPublishError, "UNSAFE_SLOT_PATH"):
            self._publish()
        self.assertEqual(self.target.read_bytes(), b"AgentOSWoWReplySlot = nil\n")

    def test_reject_when_slot_not_installed(self):
        self.target.unlink()
        with self.assertRaisesRegex(SlotPublishError, "SLOT_NOT_INSTALLED"):
            self._publish()

    def test_reject_when_slot_not_load_on_demand(self):
        (self.directory / (SLOT_NAME + ".toc")).write_bytes(b"## LoadOnDemand: 0\n")
        with self.assertRaisesRegex(SlotPublishError, "UNSUPPORTED_SLOT"):
            self._publish()

    def test_failure_preserves_old_reply_and_cleans_tmp(self):
        original = self.target.read_bytes()
        with patch("agentos_node.wow_slot_publisher.os.replace", side_effect=OSError("unsafe-secret-path")):
            with self.assertRaisesRegex(SlotPublishError, "SLOT_PUBLISH_FAILED"):
                self._publish()
        self.assertEqual(self.target.read_bytes(), original)
        self.assertFalse(list(self.directory.glob(".agentos-reply-*")))

    def test_mock_capture_to_verified_slot_write(self):
        from scripts.wow_companion_bridge_adapter import QuestionBridgeAdapter
        from scripts.wow_companion_frames import encode_question

        frame = encode_question(b"abcdefgh", 81, "Where is the mage trainer?")[0]
        captured = frame + [0] * (200 - len(frame))
        def provider(question, request_id, key):
            self.assertEqual(question, "Where is the mage trainer?")
            self.assertEqual(key, "ephemeral-test-key")
            return {
                "schema": SCHEMA, "request_id": request_id,
                "category": "general", "answer": "Ask a guard.",
                "sources": [], "action": {"type": "ui.answer"}
            }

        bridge = QuestionBridgeAdapter(
            lambda session: session == b"abcdefgh".hex(),
            lambda: "ephemeral-test-key",
            provider=provider,
        )
        result = bridge.accept_capture(captured)
        self.assertEqual(result["status"], "SLOT_READY")
        self.assertFalse(result["published"])
        published = self._publish({
            "schema": SCHEMA, "request_id": result["request_id"],
            "category": "general", "answer": "Ask a guard.",
            "sources": [], "action": {"type": "ui.answer"}
        }, request_id=result["request_id"])
        self.assertEqual(published["status"], "PUBLISHED")
        self.assertFalse(published["game_received"])
        self.assertEqual(self.target.read_bytes(), result["slot_bytes"])


    def test_authorized_capture_to_atomic_disk_reply(self):
        from scripts.wow_companion_bridge_adapter import QuestionBridgeAdapter
        from scripts.wow_companion_frames import encode_question

        def provider(question, request_id, credential):
            self.assertEqual(credential, "ephemeral-test-key")
            return {
                "schema": SCHEMA, "request_id": request_id, "category": "general",
                "answer": "Ask the guard.", "sources": [],
                "action": {"type": "ui.answer"}
            }

        bridge = QuestionBridgeAdapter(
            lambda session: session == b"abcdefgh".hex(),
            lambda: "ephemeral-test-key",
            provider=provider,
        )
        frame = encode_question(b"abcdefgh", 85, "Where is the trainer?")[0]
        captured = frame + [0] * (200 - len(frame))
        result = bridge.accept_and_publish(captured, self.directory)
        self.assertEqual(result, {
            "status": "PUBLISHED", "request_id": "ask-85",
            "published": True, "game_received": False
        })
        self.assertIn(b"AgentOSWoWReplySlot", self.target.read_bytes())
        self.assertNotIn(b"ephemeral-test-key", self.target.read_bytes())
        self.assertEqual(
            bridge.accept_and_publish(captured, self.directory)["reason"], "DUPLICATE_REQUEST"
        )

    def test_denied_capture_does_not_write_or_call_provider(self):
        from scripts.wow_companion_bridge_adapter import QuestionBridgeAdapter
        from scripts.wow_companion_frames import encode_question

        bridge = QuestionBridgeAdapter(
            lambda _: False, lambda: "ephemeral-test-key",
            provider=lambda *args: self.fail("must not bill provider"),
        )
        frame = encode_question(b"abcdefgh", 86, "Hello")[0]
        captured = frame + [0] * (200 - len(frame))
        original = self.target.read_bytes()
        self.assertEqual(
            bridge.accept_and_publish(captured, self.directory)["reason"],
            "LOCAL_SESSION_NOT_AUTHORIZED"
        )
        self.assertEqual(self.target.read_bytes(), original)

    def test_game_receipt_is_not_implied(self):
        self.assertIs(self._publish()["game_received"], False)


if __name__ == "__main__":
    unittest.main()
