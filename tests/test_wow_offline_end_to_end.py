"""Offline integration proof for the existing WoW data path.

No network, installed game, external authorization, or production receipt.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentos_node.wow_bridge_protocol import NodeBoundStatusGateway, encode
from agentos_node.wow_control_adapter import WoWControlAdapter
from agentos_node.wow_slot_publisher import publish_status_reply


def frame(request_id: int) -> list[int]:
    return encode(request_id, json.dumps({
        "action": "wow.control.status", "session": "test1234"
    }).encode("ascii"))


class OfflineEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.slot = Path(self.temp.name) / "AgentOSWoW_R001"
        self.slot.mkdir()
        (self.slot / "AgentOSWoW_R001.toc").write_text(
            "## Interface: 16001\n## LoadOnDemand: 1\nReply.lua\n",
            encoding="ascii",
        )
        self.reply = self.slot / "Reply.lua"
        self.reply.write_text("AgentOSWoWReplySlot = nil\n", encoding="ascii")

    def test_complete_offline_data_path_and_replay(self):
        calls = []
        adapter = WoWControlAdapter(lambda: (
            calls.append("reader") or
            {"state": "READY", "paw": "running", "receipt": "receipt:test-17"}
        ))
        gateway = NodeBoundStatusGateway(
            lambda: calls.append("auth") or True,
            adapter.execute,
        )
        sent = frame(17)
        outcome = publish_status_reply(sent, gateway, self.slot)
        self.assertEqual(outcome, {"status": "PUBLISHED", "request_id": 17})
        self.assertEqual(calls, ["auth", "reader"])
        lua = self.reply.read_text(encoding="ascii")
        self.assertIn("request_id = 17,", lua)
        self.assertIn('state = "READY",', lua)
        self.assertIn('receipt = "receipt:test-17",', lua)
        self.assertNotIn("test1234", lua)
        self.assertNotIn("RunScript", lua)
        self.assertEqual(publish_status_reply(sent, gateway, self.slot)["reason"],
                         "GATEWAY_REJECTED")
        self.assertEqual(self.reply.read_text(encoding="ascii"), lua)
        self.assertEqual(calls, ["auth", "reader"])

    def test_denial_never_publishes_a_reply(self):
        calls = []
        adapter = WoWControlAdapter(lambda: calls.append("reader") or {"state": "READY"})
        gateway = NodeBoundStatusGateway(lambda: False, adapter.execute)
        before = self.reply.read_bytes()
        self.assertEqual(publish_status_reply(frame(22), gateway, self.slot)["reason"],
                         "GATEWAY_REJECTED")
        self.assertEqual(self.reply.read_bytes(), before)
        self.assertEqual(calls, [])

    def test_unsafe_node_status_never_publishes_a_reply(self):
        adapter = WoWControlAdapter(lambda: {"state": "READY", "token": "private"})
        gateway = NodeBoundStatusGateway(lambda: True, adapter.execute)
        before = self.reply.read_bytes()
        self.assertEqual(publish_status_reply(frame(23), gateway, self.slot)["reason"],
                         "GATEWAY_REJECTED")
        self.assertEqual(self.reply.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
