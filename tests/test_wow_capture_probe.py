from __future__ import annotations
import json
import subprocess
import sys
import unittest
from agentos_node.wow_bridge_protocol import encode

class CaptureProbeTests(unittest.TestCase):
    def test_decode_not_authority(self):
        payload=json.dumps({"action":"wow.control.status","session":"abc12345"}).encode()
        cells=encode(42,payload)
        cells += [0]*(200-len(cells))
        r=subprocess.run([sys.executable,"-m","agentos_node.wow_capture_probe"],
                         input=json.dumps(cells),text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)
        out=json.loads(r.stdout)
        self.assertEqual(out["status"],"DECODED_UNAUTHORIZED")
        self.assertEqual(out["one_status"],"UNKNOWN")
        self.assertIsNone(out["receipt_id"])
        self.assertNotIn("abc12345",r.stdout)

    def test_reject_random_capture(self):
        r=subprocess.run([sys.executable,"-m","agentos_node.wow_capture_probe"],
                         input=json.dumps([0]*200),text=True,capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertEqual(json.loads(r.stdout)["status"],"REJECTED")

if __name__=="__main__":unittest.main()
