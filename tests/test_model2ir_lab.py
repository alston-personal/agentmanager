from __future__ import annotations

import http.client
import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from scripts import model2ir_lab_server as lab


def minimal_glb(extra: dict | None = None) -> bytes:
    doc = {"asset": {"version": "2.0"}, "nodes": [], "meshes": []}
    if extra:
        doc.update(extra)
    payload = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    chunk = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk


class Model2IRLabContractTest(unittest.TestCase):
    def test_glb_runs_real_library_contract(self):
        data = minimal_glb()
        out = lab.analyze_asset_bytes("minimal.glb", data)

        self.assertEqual(out["schema"], "model2ir-lab-analysis/v0.1")
        self.assertEqual(out["analysis_source"], "python-model2ir-library")
        self.assertEqual(out["model2ir_version"], "0.9.1")
        self.assertEqual(out["asset"]["sha256"], __import__("hashlib").sha256(data).hexdigest())
        self.assertFalse(out["asset"]["persisted"])
        self.assertTrue(out["asset"]["self_contained_standard_resources"])
        self.assertEqual(out["results"]["audit"]["repeats"], 3)
        self.assertEqual(out["results"]["extracted_ir"]["schema"], "model2ir-character-ir/v0.6")
        self.assertEqual(out["results"]["extracted_ir"]["source"]["name"], "minimal.glb")
        self.assertIn("geometry_profile", out["evidence"])
        self.assertIn("topology", out["evidence"])

    def test_vrm_suffix_uses_same_binary_container_path(self):
        out = lab.analyze_asset_bytes("character.vrm", minimal_glb())
        self.assertEqual(out["asset"]["suffix"], ".vrm")
        self.assertEqual(out["analysis_source"], "python-model2ir-library")

    def test_multifile_gltf_is_explicitly_unsupported(self):
        with self.assertRaisesRegex(lab.UnsupportedAssetError, "multi-file .gltf bundles are not supported"):
            lab.analyze_asset_bytes("character.gltf", minimal_glb())

    def test_external_buffer_uri_is_rejected_as_bundle_boundary(self):
        data = minimal_glb({"buffers": [{"byteLength": 4, "uri": "mesh.bin"}]})
        with self.assertRaisesRegex(lab.UnsupportedAssetError, "self-contained GLB/VRM"):
            lab.analyze_asset_bytes("external-buffer.glb", data)

    def test_external_image_uri_is_rejected_as_bundle_boundary(self):
        data = minimal_glb({"images": [{"uri": "textures/albedo.png"}]})
        with self.assertRaisesRegex(lab.UnsupportedAssetError, "v0.10 bundle-fidelity"):
            lab.analyze_asset_bytes("external-image.glb", data)

    def test_data_uri_is_still_self_contained(self):
        data = minimal_glb({"images": [{"uri": "data:image/png;base64,"}]})
        out = lab.analyze_asset_bytes("data-uri.glb", data)
        self.assertTrue(out["asset"]["self_contained_standard_resources"])

    def test_non_glb_bytes_are_rejected_before_model2ir(self):
        bad = b"not-a-glb-container"
        with self.assertRaisesRegex(lab.LabInputError, "GLB magic"):
            lab.analyze_asset_bytes("bad.glb", bad)

    def test_header_declared_length_must_match_upload(self):
        data = bytearray(minimal_glb())
        struct.pack_into("<I", data, 8, len(data) + 4)
        with self.assertRaisesRegex(lab.LabInputError, "declared length"):
            lab.analyze_asset_bytes("bad.glb", bytes(data))

    def test_chunk_alignment_is_strict(self):
        payload = b"{} "
        chunk = struct.pack("<II", len(payload), lab.JSON_CHUNK) + payload
        data = struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk
        with self.assertRaisesRegex(lab.LabInputError, "4-byte aligned"):
            lab.analyze_asset_bytes("unaligned.glb", data)

    def test_upload_limit_is_checked_without_large_fixture(self):
        data = minimal_glb()
        with mock.patch.object(lab, "MAX_UPLOAD_BYTES", len(data) - 1):
            with self.assertRaises(lab.PayloadTooLargeError):
                lab.analyze_asset_bytes("too-large.glb", data)

    def test_external_stabilization_is_not_laundered_to_canonical_truth(self):
        out = lab.analyze_asset_bytes("external.glb", minimal_glb())
        self.assertEqual(out["summary"]["inferred"]["result_role"], "stabilized-candidate")
        self.assertFalse(out["truth_policy"]["candidate_is_canonical"])
        self.assertFalse(out["truth_policy"]["stabilized_candidate_is_canonical"])
        self.assertFalse(out["truth_policy"]["automatic_promotion_of_inference"])
        self.assertEqual(out["summary"]["inferred"]["stabilized_body_plan"]["kind"], "unknown")

    def test_temporary_upload_is_removed_after_analysis(self):
        with tempfile.TemporaryDirectory() as temp_root:
            with mock.patch.object(tempfile, "tempdir", temp_root):
                out = lab.analyze_asset_bytes("cleanup.glb", minimal_glb())
                self.assertFalse(out["asset"]["persisted"])
                self.assertEqual(list(Path(temp_root).glob("model2ir-lab-*")), [])

    def test_filename_must_not_be_a_path(self):
        with self.assertRaisesRegex(lab.LabInputError, "basename"):
            lab.analyze_asset_bytes("../../secret.glb", minimal_glb())


class Model2IRLabHTTPTest(unittest.TestCase):
    def setUp(self):
        self.server = lab.Model2IRLabHTTPServer(("127.0.0.1", 0), lab.Model2IRLabHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        raw = response.read()
        payload = json.loads(raw.decode("utf-8")) if raw else None
        status = response.status
        response_headers = dict(response.getheaders())
        conn.close()
        return status, response_headers, payload

    def test_health_contract(self):
        status, headers, payload = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["model2ir_version"], "0.9.1")
        self.assertTrue(payload["self_contained_standard_resources_required"])
        self.assertFalse(payload["multi_file_gltf_supported"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_raw_binary_analyze_endpoint(self):
        data = minimal_glb()
        status, _, payload = self.request(
            "POST",
            "/v1/analyze",
            body=data,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Model2IR-Filename": quote("browser sample.glb"),
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        analysis = payload["analysis"]
        self.assertEqual(analysis["asset"]["filename"], "browser sample.glb")
        self.assertEqual(analysis["results"]["extracted_ir"]["source"]["name"], "browser sample.glb")
        self.assertTrue(analysis["asset"]["self_contained_standard_resources"])
        self.assertEqual(analysis["summary"]["inferred"]["result_role"], "stabilized-candidate")
        self.assertFalse(analysis["truth_policy"]["automatic_promotion_of_inference"])

    def test_gltf_endpoint_rejection_is_explicit(self):
        status, _, payload = self.request(
            "POST",
            "/v1/analyze",
            body=minimal_glb(),
            headers={"X-Model2IR-Filename": "bundle.gltf"},
        )
        self.assertEqual(status, 415)
        self.assertEqual(payload["error"], "unsupported-asset")
        self.assertIn("multi-file .gltf", payload["message"])

    def test_external_resource_endpoint_rejection_is_415(self):
        status, _, payload = self.request(
            "POST",
            "/v1/analyze",
            body=minimal_glb({"images": [{"uri": "texture.png"}]}),
            headers={"X-Model2IR-Filename": "external.glb"},
        )
        self.assertEqual(status, 415)
        self.assertEqual(payload["error"], "unsupported-asset")
        self.assertIn("self-contained", payload["message"])

    def test_oversized_content_length_is_rejected_before_read(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/analyze")
        conn.putheader("Content-Length", str(lab.MAX_UPLOAD_BYTES + 1))
        conn.putheader("X-Model2IR-Filename", "huge.glb")
        conn.endheaders()
        response = conn.getresponse()
        status = response.status
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
        self.assertEqual(status, 413)
        self.assertEqual(payload["error"], "payload-too-large")


if __name__ == "__main__":
    unittest.main()
