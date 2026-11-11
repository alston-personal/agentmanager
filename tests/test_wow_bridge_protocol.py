import json
import unittest
from agentos_node.wow_bridge_protocol import ProtocolError, encode, decode, decode_request, OfflineStatusGateway, NodeBoundStatusGateway

def frame(action="wow.control.status", session="abc12345", request_id=1):
    return encode(request_id, json.dumps({"action":action,"session":session}).encode())

class WowBridgeProtocolTest(unittest.TestCase):
    def test_round_trip(self):
        cells=frame()
        self.assertEqual(decode_request(cells),(1,"abc12345"))
        self.assertEqual(decode(cells)[0],1)

    def test_invalid_and_oversized_rejected(self):
        with self.assertRaises(ProtocolError):
            encode(1,b"X"*513)
        with self.assertRaises(ProtocolError):
            decode(frame()[:-6])
        with self.assertRaisesRegex(ProtocolError,"action_not_allowed"):
            decode_request(frame("shell.exec"))
        broken=frame()
        broken[12] = (broken[12]+1)%8
        with self.assertRaises(ProtocolError):
            decode(broken)

    def test_accepts_zero_padded_capture(self):
        cells = frame()
        self.assertLess(len(cells), 200)
        self.assertEqual(decode_request(cells + [0] * (200 - len(cells))), (1, "abc12345"))

    def test_rejects_hidden_frame_tail(self):
        cells = frame()
        with self.assertRaisesRegex(ProtocolError, "unexpected_trailing_cells"):
            decode(cells + [0, 0, 4])
        with self.assertRaisesRegex(ProtocolError, "unexpected_trailing_cells"):
            decode(cells + [False])
        with self.assertRaisesRegex(ProtocolError, "unexpected_trailing_cells"):
            decode(cells + [0, 2])


    def test_host_bound_status_requires_fresh_auth(self):
        from agentos_node.wow_control_adapter import WoWControlAdapter
        calls = []
        adapter = WoWControlAdapter(lambda: {"state": "READY", "paw": "running", "receipt": None})
        gateway = NodeBoundStatusGateway(lambda: (calls.append("verify") or True), adapter.execute)
        result = gateway.accept(frame(request_id=7))
        self.assertEqual(result, {"status": "OK", "request_id": 7,
                                  "snapshot": {"state": "READY", "paw": "running", "receipt": None}})
        self.assertEqual(calls, ["verify"])
        self.assertEqual(gateway.accept(frame(request_id=7))["reason"], "DUPLICATE_REQUEST")

    def test_host_bound_status_rejects_spoofed_or_stale_auth(self):
        from agentos_node.wow_control_adapter import WoWControlAdapter
        called = []
        reader = WoWControlAdapter(lambda: called.append(1) or {"state": "READY"})
        for denial in [False, None, "true", 1]:
            gateway = NodeBoundStatusGateway(lambda denial=denial: denial, reader.execute)
            self.assertEqual(gateway.accept(frame())["reason"], "NODE_AUTH_UNAVAILABLE")
        self.assertEqual(called, [])

    def test_host_bound_status_rejects_unsafe_response_and_reader_failures(self):
        for response, reason in [
            ({"status": "OK", "snapshot": {"state": "READY", "token": "secret"}}, "UNSAFE_NODE_RESPONSE"),
            ({"status": "OK", "snapshot": {"state": {"untrusted": 1}}}, "UNSAFE_NODE_RESPONSE"),
            ({"status": "UNAVAILABLE", "reason": "RUNTIME_READER_NOT_BOUND"}, "NODE_READER_UNAVAILABLE"),
            ("unexpected", "NODE_READER_UNAVAILABLE"),
        ]:
            gateway = NodeBoundStatusGateway(lambda: True, lambda _, response=response: response)
            output = gateway.accept(frame())
            self.assertEqual(output["reason"], reason)
            self.assertNotIn("snapshot", output)

    def test_host_bound_status_rejects_replay_capacity_exhaustion(self):
        gateway = NodeBoundStatusGateway(lambda: True,
                lambda _: {"status": "OK", "snapshot": {"state": "READY"}}, max_seen=1)
        self.assertEqual(gateway.accept(frame( request_id=1))["status"], "OK")
        self.assertEqual(gateway.accept(frame( request_id=2))["reason"], "REPLAY_CAPACITY_EXHAUSTED")

    def test_host_bound_status_rejects_probe_or_reader_exception(self):
        def fail(*_):
            raise RuntimeError("never leak credentials")
        self.assertEqual(NodeBoundStatusGateway(fail, lambda _: {}).accept(frame())["reason"], "NODE_AUTH_UNAVAILABLE")
        self.assertEqual(NodeBoundStatusGateway(lambda: True, fail).accept(frame())["reason"], "NODE_READER_UNAVAILABLE")

    def test_account_intents_are_distinct_from_status_and_cannot_supply_realm(self):
        from agentos_node.wow_bridge_protocol import decode_account_intent, NodeBoundAccountGateway
        def intent(action, request_id=5):
            return frame(action=action, request_id=request_id)
        self.assertEqual(decode_account_intent(intent("wow.account.login.start")), (5, "abc12345", "wow.account.login.start"))
        with self.assertRaisesRegex(ProtocolError, "action_not_allowed"):
            decode_request(intent("wow.account.logout"))
        with self.assertRaisesRegex(ProtocolError, "account_action_not_allowed"):
            decode_account_intent(intent("shell.exec"))
        with self.assertRaisesRegex(ProtocolError, "invalid_request_shape"):
            decode_account_intent(encode(6, json.dumps({"action":"wow.account.login.start","session":"abc12345","realm":"realm-alston"}).encode()))
        called = []
        gate = NodeBoundAccountGateway(lambda: True, lambda action: called.append(action) or {"status":"PAIRING_STARTED"})
        self.assertEqual(gate.accept(intent("wow.account.login.start"))["status"], "PAIRING_STARTED")
        self.assertEqual(called, ["wow.account.login.start"])
        self.assertEqual(gate.accept(intent("wow.account.login.start"))["reason"], "DUPLICATE_REQUEST")
        self.assertEqual(NodeBoundAccountGateway(lambda: False, lambda _: {}).accept(intent("wow.account.logout"))["reason"], "BRIDGE_NOT_AUTHORIZED")
        self.assertEqual(NodeBoundAccountGateway(lambda: True, lambda _: {"status":"SIGNED_OUT","token":"secret"}).accept(intent("wow.account.logout"))["reason"], "UNSAFE_ACCOUNT_RESPONSE")

    def test_no_auth_no_fake_status(self):
        gateway=OfflineStatusGateway()
        self.assertEqual(gateway.accept(frame())["reason"],"ONE_NOT_BOUND")
        self.assertTrue(gateway.accept(frame())["duplicate"])
if __name__=="__main__":
    unittest.main()
