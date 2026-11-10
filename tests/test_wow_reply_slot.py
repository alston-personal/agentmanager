from __future__ import annotations

import unittest

from agentos_node.wow_reply_slot import render_reply_slot
from agentos_node.wow_status_reply import encode_status_reply


class ReplySlotTests(unittest.TestCase):
    def test_data_only_rendering(self):
        payload = encode_status_reply({
            "status": "OK", "request_id": 33,
            "snapshot": {"state": "READY", "paw": "running", "receipt": "receipt:33"},
        })
        text = render_reply_slot(payload, expected_request_id=33).decode("ascii")
        self.assertIn("AgentOSWoWReplySlot = {", text)
        self.assertIn("request_id = 33,", text)
        self.assertIn('receipt = "receipt:33"', text)
        self.assertNotIn("loadstring", text)
        self.assertNotIn("RunScript", text)

    def test_cannot_inject_lua_or_mismatch_request(self):
        payload = encode_status_reply({
            "status": "OK", "request_id": 33, "snapshot": {"state": "READY"}
        })
        with self.assertRaisesRegex(ValueError, "mismatched_reply_id"):
            render_reply_slot(payload, expected_request_id=34)
        with self.assertRaises(ValueError):
            encode_status_reply({
                "status": "OK", "request_id": 33,
                "snapshot": {"state": 'READY"; RunScript("evil")'},
            })


if __name__ == "__main__":
    unittest.main()
