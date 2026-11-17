import copy
import unittest
from scripts.wow_companion_reply import SCHEMA, ReplyValidationError, validate_reply


class WowCompanionReplyTests(unittest.TestCase):
    def setUp(self):
        self.msg = {
            "schema": SCHEMA, "request_id": "ask-42", "category": "npc",
            "answer": "The NPC is near the east gate.",
            "sources": [{"title": "NPC reference", "url": "https://example.org/npc/42"}],
            "action": {"type": "map.waypoint", "map_id": 12,
                       "x": 0.42, "y": 0.67, "label": "East gate"}
        }

    def test_waypoint_is_data_only(self):
        self.assertEqual(validate_reply(self.msg, "ask-42")["action"]["x"], .42)

    def test_answer_without_waypoint(self):
        self.msg["sources"] = []
        self.msg["action"] = {"type": "ui.answer"}
        self.assertEqual(validate_reply(self.msg, "ask-42")["action"]["type"], "ui.answer")

    def test_replay_rejected(self):
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-43")

    def test_untrusted_game_action_rejected(self):
        self.msg["action"] = {"type": "wow.cast", "spell": 1}
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")

    def test_extra_executable_field_rejected(self):
        self.msg["action"]["lua"] = "RunScript('X')"
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")

    def test_bad_coordinates_rejected(self):
        for coord in [-1, 2, True, "0.2", float("nan"), float("inf")]:
            with self.subTest(coord=coord):
                m = copy.deepcopy(self.msg)
                m["action"]["x"] = coord
                with self.assertRaises(ReplyValidationError):
                    validate_reply(m, "ask-42")

    def test_markup_rejected(self):
        self.msg["answer"] = "|Hitem:1|h[Click]|h"
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")

    def test_http_source_rejected(self):
        self.msg["sources"][0]["url"] = "http://example.org/foo"
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")

    def test_waypoint_needs_source(self):
        self.msg["sources"] = []
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")

    def test_unexpected_root_fields_rejected(self):
        self.msg["shell"] = "whoami"
        with self.assertRaises(ReplyValidationError):
            validate_reply(self.msg, "ask-42")


if __name__ == "__main__":
    unittest.main()
