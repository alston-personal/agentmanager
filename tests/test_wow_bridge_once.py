"""One-shot WoW Bridge: fresh Node/ONE heartbeat is required before reply."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentos_node.wow_bridge_protocol import encode
from agentos_node.wow_bridge_once import process_probe


class OneShotBridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.slot = self.root / "AgentOSWoW_R001"
        self.slot.mkdir()
        (self.slot / "AgentOSWoW_R001.toc").write_text(
            "## Interface: 16001\n## LoadOnDemand: 1\nReply.lua\n", encoding="ascii"
        )
        self.reply = self.slot / "Reply.lua"
        self.reply.write_text("AgentOSWoWReplySlot = nil\n", encoding="ascii")
        self.frame = encode(19, json.dumps({
            "action": "wow.control.status", "session": "demo123456"
        }).encode("ascii"))

    def check(self, factory, frame=None):
        return process_probe(self.frame if frame is None else frame,
                             config_path=self.root / "no-config",
                             policy_path=self.root / "no-policy",
                             slot_dir=self.slot, node_factory=factory)

    def test_fresh_accepted_heartbeat_creates_display_only_status(self):
        called = []
        class Transport:
            def heartbeat(self):
                called.append("heartbeat")
                return {"heartbeat_recorded": True, "ok": True}
        result = self.check(lambda: Transport())
        self.assertEqual(result, {"status": "PUBLISHED", "request_id": 19})
        self.assertEqual(called, ["heartbeat"])
        lua = self.reply.read_text(encoding="ascii")
        self.assertIn('state = "NODE_ONLINE"', lua)
        self.assertIn('paw = "unverified"', lua)
        self.assertIn('receipt = false', lua)
        self.assertNotIn("demo123456", lua)
        self.assertNotIn("node_token", lua)

    def test_rejected_or_missing_heartbeat_never_writes(self):
        for response in ({}, {"ok": True}, {"heartbeat_recorded": "true"},
                         {"heartbeat_recorded": False}, {"heartbeat_recorded": None}):
            with self.subTest(response=response):
                before = self.reply.read_bytes()
                class Transport:
                    def heartbeat(self):
                        return response
                self.assertEqual(self.check(lambda: Transport())["status"], "UNAVAILABLE")
                self.assertEqual(self.reply.read_bytes(), before)

    def test_failed_network_never_writes(self):
        before = self.reply.read_bytes()
        class Offline:
            def heartbeat(self):
                raise OSError("secret credential must not escape")
        self.assertEqual(self.check(lambda: Offline())["reason"], "GATEWAY_REJECTED")
        self.assertEqual(self.reply.read_bytes(), before)

    def test_game_cannot_choose_realm_or_action(self):
        before = self.reply.read_bytes()
        invalid = encode(19, json.dumps({
            "action": "wow.control.status", "session": "demo123456",
            "realm_id": "realm-u-"+"a"*24
        }).encode("ascii"))
        with self.assertRaises(ValueError):
            self.check(lambda: None, invalid)
        self.assertEqual(self.reply.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
