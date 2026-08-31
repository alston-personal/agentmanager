from __future__ import annotations

import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from model2ir import GEOMETRY_PROFILE_SCHEMA, extract_ir, profile_asset_structure
from model2ir.__main__ import main


REFERENCE = Path(__file__).parent / "fixtures" / "model2ir" / "meshy_foxfire_weak_structure_reference.json"


def write_reference_glb(path: Path, reference: dict) -> None:
    observed = reference["observed"]
    extent = observed["bbox_extent_local_untransformed"]
    gltf = {
        "asset": {"version": "2.0", "generator": reference["source"]["generator"]},
        "accessors": [
            {
                "componentType": 5126,
                "count": observed["vertices_sum"],
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": extent,
            },
            {
                "componentType": 5125,
                "count": observed["indices_sum"],
                "type": "SCALAR",
            },
        ],
        "materials": [{"name": "material"}],
        "meshes": [
            {
                "name": "mesh",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "nodes": [{"mesh": 0, "name": "mesh_node"}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }
    payload = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    json_chunk = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(json_chunk)) + json_chunk)


class Model2IRGeometryProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    def test_measurement_derived_meshy_reference_is_weak_relief_not_humanoid_truth(self):
        observed = self.reference["observed"]
        model_ir = {
            "structural_ir": {
                "geometry": {
                    "bbox": {"extent_local_untransformed": observed["bbox_extent_local_untransformed"]},
                    "mesh_count": observed["mesh_count"],
                    "primitive_count": observed["primitive_count"],
                    "component_count": observed["component_count"],
                    "skin_count": observed["skin_count"],
                    "animation_count": observed["animation_count"],
                }
            },
            "semantic_evidence_v03": {"skeleton": {"joint_count": observed["joint_count"]}},
        }

        profile = profile_asset_structure(model_ir)
        expected = self.reference["expected"]

        self.assertEqual(profile["schema"], GEOMETRY_PROFILE_SCHEMA)
        self.assertEqual(profile["inferred"]["shape_hint"], expected["shape_hint"])
        self.assertEqual(profile["inferred"]["structural_signal"], expected["structural_signal"])
        self.assertEqual(profile["inferred"]["thin_axis_ratio"], expected["thin_axis_ratio"])
        self.assertEqual(profile["inferred"]["middle_axis_ratio"], expected["middle_axis_ratio"])
        self.assertIn("thin-axis-geometry", profile["inferred"]["reasons"])
        self.assertIn("no-skin", profile["inferred"]["reasons"])
        self.assertIn("no-joints", profile["inferred"]["reasons"])

    def test_integrated_extract_keeps_meshy_like_body_plan_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            asset = Path(td) / "meshy-reference.glb"
            write_reference_glb(asset, self.reference)
            extracted = extract_ir(asset)

        profile = extracted["geometry_profile_evidence"]
        candidate = extracted["candidate_ir"]
        self.assertEqual(profile["inferred"]["shape_hint"], "planar-or-relief-like")
        self.assertEqual(profile["inferred"]["structural_signal"], "weak")
        self.assertEqual(candidate["body_plan"]["kind"], "unknown")
        self.assertEqual(candidate["parts"], [])
        self.assertEqual(candidate["topology_evidence"]["kind"], "unknown")
        self.assertEqual(candidate["topology_evidence"]["reason"], "too-few-joints")

    def test_volumetric_unrigged_mesh_is_not_forced_into_weak_relief_class(self):
        profile = profile_asset_structure(
            {
                "structural_ir": {
                    "geometry": {
                        "bbox": {"extent_local_untransformed": [1.0, 1.0, 1.0]},
                        "mesh_count": 1,
                        "primitive_count": 1,
                        "component_count": 1,
                        "skin_count": 0,
                        "animation_count": 0,
                    }
                },
                "semantic_evidence_v03": {"skeleton": {"joint_count": 0}},
            }
        )
        self.assertEqual(profile["inferred"]["shape_hint"], "volumetric-like")
        self.assertEqual(profile["inferred"]["structural_signal"], "indeterminate")

    def test_profile_cli_returns_only_profile_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            asset = Path(td) / "meshy-reference.glb"
            output = Path(td) / "profile.json"
            write_reference_glb(asset, self.reference)
            buf = StringIO()
            with mock.patch("sys.argv", ["model2ir", "profile", str(asset), "-o", str(output)]), redirect_stdout(buf):
                main()
            status = json.loads(buf.getvalue().strip())
            profile = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(status["ok"])
        self.assertEqual(status["schema"], GEOMETRY_PROFILE_SCHEMA)
        self.assertEqual(profile["inferred"]["structural_signal"], "weak")


if __name__ == "__main__":
    unittest.main()
