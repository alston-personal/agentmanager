from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentos_node.wow_bridge_protocol import NodeBoundStatusGateway, encode
from agentos_node.wow_control_adapter import WoWControlAdapter
from agentos_node.wow_slot_publisher import SlotPublishError, publish_status_reply


def status_frame(request_id=15):
    return encode(request_id, json.dumps({
        "action": "wow.control.status", "session": "abc12345",
    }).encode("ascii"))


class ReplyPublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.slot = self.root / "AgentOSWoW_R001"
        self.slot.mkdir()
        (self.slot / "AgentOSWoW_R001.toc").write_text(
            "## Interface: 16001\n## LoadOnDemand: 1\nReply.lua\n", encoding="ascii"
        )
        self.reply = self.slot / "Reply.lua"
        self.reply.write_text("AgentOSWoWReplySlot = nil\n", encoding="ascii")

    def gateway(self, authorized=True):
        adapter = WoWControlAdapter(lambda: {
            "state": "READY", "paw": "running", "receipt": "receipt:15"
        })
        return NodeBoundStatusGateway(lambda: authorized, adapter.execute)

    def test_authorized_atomic_publish(self):
        result = publish_status_reply(status_frame(), self.gateway(), self.slot)
        self.assertEqual(result, {"status": "PUBLISHED", "request_id": 15})
        rendered = self.reply.read_text(encoding="ascii")
        self.assertIn("request_id = 15,", rendered)
        self.assertIn('receipt = "receipt:15"', rendered)
        self.assertEqual(sorted(p.name for p in self.slot.iterdir()),
                         ["AgentOSWoW_R001.toc", "Reply.lua"])

    def test_unauthorized_cannot_change_slot(self):
        original = self.reply.read_bytes()
        result = publish_status_reply(status_frame(), self.gateway(False), self.slot)
        self.assertEqual(result["reason"], "GATEWAY_REJECTED")
        self.assertEqual(self.reply.read_bytes(), original)

    def test_replay_does_not_publish_twice(self):
        gateway = self.gateway()
        publish_status_reply(status_frame(), gateway, self.slot)
        self.reply.write_text("sentinel", encoding="ascii")
        self.assertEqual(publish_status_reply(status_frame(), gateway, self.slot)["status"], "UNAVAILABLE")
        self.assertEqual(self.reply.read_text(encoding="ascii"), "sentinel")

    def test_reject_wrong_response_id(self):
        original = self.reply.read_bytes()
        class WrongId:
            def accept(self, _):
                return {"status": "OK", "request_id": 14,
                        "snapshot": {"state": "READY"}}
        self.assertEqual(publish_status_reply(status_frame(), WrongId(), self.slot)["reason"],
                         "CORRELATION_REJECTED")
        self.assertEqual(self.reply.read_bytes(), original)

    def test_preinstalled_slot_only(self):
        wrong = self.root / "Untrusted"
        wrong.mkdir()
        with self.assertRaisesRegex(SlotPublishError, "INVALID_SLOT_DIRECTORY"):
            publish_status_reply(status_frame(), self.gateway(), wrong)
        self.reply.unlink()
        with self.assertRaisesRegex(SlotPublishError, "SLOT_NOT_INSTALLED"):
            publish_status_reply(status_frame(), self.gateway(), self.slot)
        self.assertFalse(self.reply.exists())

    def test_symlink_target_rejected(self):
        self.reply.unlink()
        outside = self.root / "outside.txt"
        outside.write_text("untouched", encoding="ascii")
        try:
            self.reply.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable on this host")
        with self.assertRaisesRegex(SlotPublishError, "UNSAFE_SLOT_PATH"):
            publish_status_reply(status_frame(), self.gateway(), self.slot)
        self.assertEqual(outside.read_text(encoding="ascii"), "untouched")


if __name__ == "__main__":
    unittest.main()
