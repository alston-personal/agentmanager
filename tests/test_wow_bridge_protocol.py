import json
import unittest
from agentos_node.wow_bridge_protocol import ProtocolError, encode, decode, decode_request, OfflineStatusGateway

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

    def test_no_auth_no_fake_status(self):
        gateway=OfflineStatusGateway()
        self.assertEqual(gateway.accept(frame())["reason"],"ONE_NOT_BOUND")
        self.assertTrue(gateway.accept(frame())["duplicate"])
if __name__=="__main__":
    unittest.main()
