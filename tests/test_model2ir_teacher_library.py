from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from model2ir.teacher import (
    CANONICAL_VIEWS,
    TEACHER_DATASET_SCHEMA,
    TeacherDatasetError,
    build_teacher_dataset,
    validate_teacher_dataset_manifest,
)


class TeacherDatasetLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.asset = self.root / "source.glb"
        self.asset.write_bytes(b"synthetic-glb-for-library-boundary-test")
        self.out = self.root / "dataset"
        self.stable_ir = {
            "schema": "character-ir-candidate/v0.6",
            "truth_status": "candidate",
            "body_plan": {"kind": "humanoid", "confidence": 0.9},
            "parts": [{"id": "torso", "state": "inferred", "confidence": 0.8}],
            "unresolved": [{"field": "left_right_assignment", "reason": "test ambiguity"}],
        }
        self.audit = {
            "status": "stable-candidate",
            "candidate_repeatable": True,
            "semantic_authority": "inferred",
        }

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def renderer(_asset: Path, case_dir: Path):
        renders = {}
        for view in CANONICAL_VIEWS:
            name = f"canonical-{view}.png"
            (case_dir / name).write_bytes(("image:" + view).encode("utf-8"))
            renders[view] = name
        return renders

    def build(self):
        raw = {"candidate_ir": self.stable_ir}
        with (
            mock.patch("model2ir.teacher.audit_source_asset", return_value=self.audit),
            mock.patch("model2ir.teacher.extract_ir", return_value=raw),
            mock.patch("model2ir.teacher.stabilize_external_ir", return_value=self.stable_ir),
        ):
            return build_teacher_dataset(
                self.asset,
                "teacher-a",
                self.out,
                renderer=self.renderer,
            )

    def test_library_builds_v07_manifest_without_repo_renderer_dependency(self):
        manifest = self.build()
        self.assertEqual(manifest["schema"], TEACHER_DATASET_SCHEMA)
        self.assertEqual([x["view"] for x in manifest["examples"]], list(CANONICAL_VIEWS))
        self.assertEqual(len({x["target_ir_digest"] for x in manifest["examples"]}), 1)
        self.assertTrue(all("unresolved" in x for x in manifest["examples"]))
        self.assertFalse(manifest["policy"]["external_first_import_claimed_lossless"])
        self.assertTrue((self.out / "teacher-a" / "character-ir.json").is_file())
        self.assertTrue((self.out / "teacher-a" / "audit.json").is_file())
        validate_teacher_dataset_manifest(manifest, root=self.out)

    def test_validator_detects_render_tampering(self):
        manifest = self.build()
        image = self.out / manifest["examples"][0]["image"]
        image.write_bytes(b"tampered")
        with self.assertRaisesRegex(TeacherDatasetError, "image digest mismatch"):
            validate_teacher_dataset_manifest(manifest, root=self.out)

    def test_case_id_cannot_escape_dataset_root(self):
        with self.assertRaisesRegex(TeacherDatasetError, "safe path segment"):
            build_teacher_dataset(self.asset, "../escape", self.out, renderer=self.renderer)

    def test_unstable_asset_is_not_admitted(self):
        with mock.patch("model2ir.teacher.audit_source_asset", return_value={"status": "unstable"}):
            with self.assertRaisesRegex(TeacherDatasetError, "unstable"):
                build_teacher_dataset(self.asset, "unstable", self.out, renderer=self.renderer)

    def test_manifest_on_disk_matches_returned_manifest(self):
        manifest = self.build()
        disk = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(disk, manifest)


if __name__ == "__main__":
    unittest.main()
