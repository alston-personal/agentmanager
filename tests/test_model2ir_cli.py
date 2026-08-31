from __future__ import annotations

import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from model2ir.__main__ import main


def write_minimal_glb(path: Path) -> None:
    payload = json.dumps({"asset": {"version": "2.0"}, "nodes": [], "meshes": []}, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    chunk = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk)


class Model2IRCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> dict:
        buf = StringIO()
        with mock.patch("sys.argv", ["model2ir", *args]), redirect_stdout(buf):
            main()
        return json.loads(buf.getvalue().strip())

    def test_stabilize_accepts_glb_and_emits_character_ir(self):
        asset = self.root / "minimal.glb"
        output = self.root / "stable.json"
        write_minimal_glb(asset)

        status = self.run_cli("stabilize", str(asset), "-o", str(output))
        stable = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(status["ok"])
        self.assertEqual(status["schema"], "character-ir-candidate/v0.6")
        self.assertEqual(stable["schema"], "character-ir-candidate/v0.6")
        self.assertNotIn("asset", stable)

    def test_stabilize_accepts_vrm_container_suffix(self):
        asset = self.root / "minimal.vrm"
        output = self.root / "stable-vrm.json"
        write_minimal_glb(asset)

        self.run_cli("stabilize", str(asset), "-o", str(output))
        stable = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(stable["schema"], "character-ir-candidate/v0.6")

    def test_extract_keeps_full_model2ir_envelope(self):
        asset = self.root / "minimal.glb"
        output = self.root / "extract.json"
        write_minimal_glb(asset)

        self.run_cli("extract", str(asset), "-o", str(output))
        extracted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(extracted["schema"], "model2ir-character-ir/v0.6")
        self.assertIn("candidate_ir", extracted)
        self.assertIn("topology_evidence", extracted)

    def test_audit_rejects_zero_repeats_at_cli_boundary(self):
        asset = self.root / "minimal.glb"
        output = self.root / "audit.json"
        write_minimal_glb(asset)
        with self.assertRaisesRegex(SystemExit, "repeats must be >= 1"):
            self.run_cli("audit", str(asset), "-o", str(output), "--repeats", "0")


if __name__ == "__main__":
    unittest.main()
