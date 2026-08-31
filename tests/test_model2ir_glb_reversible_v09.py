from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from model2ir import extract_ir
from model2ir.glb_container import (
    BIN_CHUNK,
    JSON_CHUNK,
    compile_reversible_glb,
    parse_glb_container,
    save_reversible_glb,
    verify_glb_container_preservation,
)

CUSTOM_CHUNK = 0x1234ABCD


def _pad(payload: bytes, byte: bytes) -> bytes:
    return payload + byte * ((4 - len(payload) % 4) % 4)


def make_glb(gltf: dict, bin_payload: bytes, *, custom_payload: bytes | None = None) -> bytes:
    json_payload = _pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    bin_payload = _pad(bin_payload, b"\x00")
    chunks = [(JSON_CHUNK, json_payload), (BIN_CHUNK, bin_payload)]
    if custom_payload is not None:
        chunks.append((CUSTOM_CHUNK, _pad(custom_payload, b"\x00")))
    body = b"".join(struct.pack("<II", len(payload), kind) + payload for kind, payload in chunks)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


class ReversibleGlbV09Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ir = {
            "schema": "character-ir/v0.6",
            "identity": {"archetype": "humanoid", "locked": True},
            "body": {"plan": "humanoid"},
            "unresolved": [{"field": "hair", "reason": "not asserted"}],
        }
        self.gltf = {
            "asset": {"version": "2.0", "generator": "model2ir-v09-test"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"name": "Body", "mesh": 0}],
            "meshes": [{"name": "Body", "primitives": []}],
            "buffers": [{"byteLength": 12}],
        }
        self.bin_payload = b"\x01\x02geometry\x00\xff"
        self.custom_payload = b"opaque-custom-chunk"

    def tearDown(self):
        self.tmp.cleanup()

    def test_compile_preserves_every_non_json_chunk_byte_for_byte(self):
        source = make_glb(self.gltf, self.bin_payload, custom_payload=self.custom_payload)
        compiled = compile_reversible_glb(source, self.ir)
        src = parse_glb_container(source)
        dst = parse_glb_container(compiled)

        src_non_json = [(c.type, c.payload) for c in src.chunks if c.type != JSON_CHUNK]
        dst_non_json = [(c.type, c.payload) for c in dst.chunks if c.type != JSON_CHUNK]
        self.assertEqual(src_non_json, dst_non_json)

        report = verify_glb_container_preservation(source, compiled, self.ir)
        self.assertTrue(report["canonical_ir"]["lossless"])
        self.assertTrue(report["container"]["json_expected"])
        self.assertTrue(report["container"]["non_json_chunks_exact"])
        self.assertTrue(report["lossless_reversible"])
        self.assertEqual(report["container"]["non_json_chunk_count"], 2)

    def test_saved_glb_reimports_exact_canonical_ir_and_source_is_unchanged(self):
        source_path = self.root / "source.glb"
        output_path = self.root / "reversible.glb"
        source_path.write_bytes(make_glb(self.gltf, self.bin_payload))
        source_before = hashlib.sha256(source_path.read_bytes()).hexdigest()

        save_reversible_glb(source_path, self.ir, output_path)

        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), source_before)
        recovered = extract_ir(output_path)
        self.assertTrue(recovered["reversibility"]["lossless"])
        self.assertEqual(recovered["canonical_ir"], self.ir)
        self.assertTrue(
            verify_glb_container_preservation(source_path, output_path, self.ir)["lossless_reversible"]
        )

    def test_vrm_suffix_uses_same_binary_container_contract(self):
        source_path = self.root / "source.vrm"
        output_path = self.root / "reversible.vrm"
        source_path.write_bytes(make_glb(self.gltf, self.bin_payload))

        save_reversible_glb(source_path, self.ir, output_path)
        recovered = extract_ir(output_path)
        self.assertEqual(recovered["source_kind"], "vrm")
        self.assertEqual(recovered["canonical_ir"], self.ir)

    def test_relative_external_resources_are_rejected_by_default(self):
        external = dict(self.gltf)
        external["images"] = [{"uri": "textures/body.png"}]
        source = make_glb(external, self.bin_payload)
        with self.assertRaisesRegex(ValueError, "external resources"):
            compile_reversible_glb(source, self.ir)

    def test_writer_refuses_in_place_overwrite(self):
        source_path = self.root / "source.glb"
        source_path.write_bytes(make_glb(self.gltf, self.bin_payload))
        with self.assertRaisesRegex(ValueError, "overwrite source"):
            save_reversible_glb(source_path, self.ir, source_path)

    def test_declared_length_mismatch_is_rejected(self):
        source = bytearray(make_glb(self.gltf, self.bin_payload))
        struct.pack_into("<I", source, 8, len(source) - 4)
        with self.assertRaisesRegex(ValueError, "declared length mismatch"):
            parse_glb_container(source)


if __name__ == "__main__":
    unittest.main()
