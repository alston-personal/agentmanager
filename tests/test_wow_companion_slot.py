import unittest

from scripts.wow_companion_reply import SCHEMA
from scripts.wow_companion_slot import (
    MAX_SLOT_BYTES, CompanionSlotError, render_companion_slot
)


class WoWCompanionSlotTests(unittest.TestCase):
    def make_reply(self, answer="Hello"):
        return {"schema": SCHEMA, "request_id": "ask-42",
                "category": "general", "answer": answer, "sources": [],
                "action": {"type": "ui.answer"}}

    def test_renders_data_only_legacy_slot_symbol(self):
        slot = render_companion_slot(self.make_reply(), "ask-42")
        self.assertIn(b"AgentOSWoWReplySlot = {", slot)
        self.assertIn(b"schema = ", slot)
        self.assertIn(b"answer = ", slot)
        self.assertNotIn(b"loadstring", slot)
        self.assertLessEqual(len(slot), MAX_SLOT_BYTES)

    def test_literal_lua_injection_is_escaped(self):
        malicious = '"); RunScript("x"); --'
        slot = render_companion_slot(self.make_reply(malicious), "ask-42")
        self.assertNotIn(b'RunScript(', slot)
        self.assertNotIn(b'");', slot)
        self.assertIn(b"\\082\\117\\110", slot)

    def test_unicode_answer_encoded_as_byte_escapes(self):
        slot = render_companion_slot(self.make_reply("你好，法師"), "ask-42")
        self.assertTrue(slot.isascii())
        self.assertIn(b"\\228\\189", slot)

    def test_replay_correlation_fails(self):
        with self.assertRaises(ValueError):
            render_companion_slot(self.make_reply(), "ask-43")

    def test_waypoint_disallowed_until_nav_adapter_review(self):
        msg = self.make_reply()
        msg["sources"] = [{"title": "Source", "url": "https://example.org"}]
        msg["action"] = {"type": "map.waypoint", "map_id": 1,
                         "x": .5, "y": .5, "label": "Example"}
        with self.assertRaises(CompanionSlotError):
            render_companion_slot(msg, "ask-42")

    def test_large_reply_fails_closed(self):
        with self.assertRaises(ValueError):
            render_companion_slot(self.make_reply("x" * 1201), "ask-42")


if __name__ == "__main__":
    unittest.main()
