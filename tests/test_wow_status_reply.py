from __future__ import annotations

import json
import unittest

from agentos_node.wow_status_reply import (
    MAX_REPLY_BYTES, REPLY_SCHEMA, decode_status_reply, encode_status_reply,
)


class StatusReplyCodecTests(unittest.TestCase):
    def test_round_trip_and_request_correlation(self):
        original = {"status": "OK", "request_id": 42,
                    "snapshot": {"state": "READY", "paw": "running", "receipt": "receipt:42"}}
        payload = encode_status_reply(original)
        self.assertLessEqual(len(payload), MAX_REPLY_BYTES)
        self.assertEqual(json.loads(payload)["schema"], REPLY_SCHEMA)
        self.assertEqual(decode_status_reply(payload, expected_request_id=42),
                         {"request_id": 42, "snapshot": original["snapshot"]})
        with self.assertRaisesRegex(ValueError, "mismatched_reply_id"):
            decode_status_reply(payload, expected_request_id=41)

    def test_denied_or_extra_gateway_result_is_never_encoded(self):
        for result in [
            {"status": "UNAVAILABLE", "reason": "NODE_AUTH_UNAVAILABLE"},
            {"status": "OK", "request_id": 1, "snapshot": {"state": "READY"}, "token": "secret"},
            {"status": "OK", "request_id": 1, "snapshot": {"state": "READY", "secret": "token"}},
            {"status": "OK", "request_id": True, "snapshot": {"state": "READY"}},
            {"status": "OK", "request_id": 65536, "snapshot": {"state": "READY"}},
            {"status": "OK", "request_id": 1, "snapshot": {}},
        ]:
            with self.subTest(result=result), self.assertRaises(ValueError):
                encode_status_reply(result)

    def test_rejects_untrusted_or_malformed_wire_payloads(self):
        original = {"status": "OK", "request_id": 1, "snapshot": {"state": "READY"}}
        good = json.loads(encode_status_reply(original))
        for bad in [
            dict(good, token="secret"),
            dict(good, status="UNAVAILABLE"),
            dict(good, schema="unknown"),
            dict(good, request_id=True),
            dict(good, snapshot={"state": "READY", "path": "sensitive"}),
            dict(good, snapshot={"paw": "x" * 100}),
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decode_status_reply(json.dumps(bad).encode(), expected_request_id=1)
        for payload in [b"not-json", b"{" + b"x" * MAX_REPLY_BYTES, "bad", b"\xff"]:
            with self.subTest(payload=repr(payload)[:20]), self.assertRaises(ValueError):
                decode_status_reply(payload, expected_request_id=1)


if __name__ == "__main__":
    unittest.main()
