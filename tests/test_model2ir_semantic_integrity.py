from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from model2ir import (
    audit_asset, compile_reversible_glb, compile_reversible_gltf, diff_ir,
    extract_ir, reconcile_ir, score_roundtrip, stabilize_external_ir,
)
from model2ir.core import Asset
from model2ir.reversible import EXTENSION_KEY, ir_digest, recover_embedded_ir
from test_model2ir_glb_reversible_v09 import make_glb


def evidence(name):
    gltf = {"asset": {"version": "2.0"}, "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": []}]}
    return extract_ir(Asset(Path(name + ".gltf"), "gltf", gltf, 0, []))


class SemanticIntegrityTest(unittest.TestCase):
    def test_new_envelopes_do_not_report_disjoint_parts_as_equal(self):
        a, b = evidence("head"), evidence("hair")
        result = diff_ir(a, b)["semantic"]
        self.assertEqual(result["jaccard"], 0.0)
        self.assertEqual(result["only_a"], ["head"])
        self.assertEqual(result["only_b"], ["hair"])
        self.assertEqual(score_roundtrip(a, b)["semantic_preservation"], 0.0)

    def test_all_envelope_versions_and_direct_candidates_keep_labels(self):
        image = {"inferred": {"parts": ["head"]}}
        for version in ("0.1", "0.2", "0.4", "0.6"):
            model = evidence("head")
            model["schema"] = "model2ir-character-ir/v" + version
            with self.subTest(version=version):
                self.assertEqual(reconcile_ir(image, model)["semantic_recovery_ratio"], 1.0)
        candidate = stabilize_external_ir(evidence("head"))
        self.assertEqual(diff_ir(image, candidate)["semantic"]["jaccard"], 1.0)
        self.assertEqual(reconcile_ir(image, candidate)["matched"], ["head"])

    def test_embedded_payload_is_compared_instead_of_carrier_names(self):
        model = evidence("hair")
        model["canonical_ir"] = {"schema": "character-ir/v0.6", "parts": [{"id": "head"}]}
        self.assertEqual(diff_ir({"inferred": {"parts": ["head"]}}, model)["semantic"]["jaccard"], 1.0)

    def test_legacy_v01_candidates_without_v03_evidence(self):
        model = {"schema": "model2ir-character-ir/v0.1", "semantic_ir": {
            "candidates": [{"semantic_candidate": {"label": "head"}}]}}
        self.assertEqual(reconcile_ir({"inferred": {"parts": ["head"]}}, model)["matched"], ["head"])

    def test_empty_and_unknown_labels_do_not_become_parts(self):
        self.assertEqual(diff_ir({"parts": ["unknown", None, {}]}, {"parts": []})["semantic"]["shared"], [])

    def test_ribbon_tail_is_accessory_but_animal_tail_remains_tail(self):
        for name in ("RibbonTail", "ribbon_tail", "BowTail"):
            with self.subTest(name=name):
                self.assertNotIn("tail", evidence(name)["semantic_evidence_v03"]["parts"])
                self.assertIn("accessory", evidence(name)["semantic_evidence_v03"]["parts"])
        for name in ("Tail", "FoxTail", "tail_01", "RainbowTail"):
            self.assertIn("tail", evidence(name)["semantic_evidence_v03"]["parts"])
        self.assertIn("hair", evidence("PonyTail")["semantic_evidence_v03"]["parts"])


class CanonicalBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.gltf = {"asset": {"version": "2.0"}}
        self.source = make_glb(self.gltf, b"original-geometry")

    def test_both_writers_reject_explicit_candidate_statuses(self):
        for status in ("candidate", "inferred", "unknown", "stable-candidate",
                       "stable-unknown", "stable-but-ambiguous", "STABLE_CANDIDATE"):
            ir = {"schema": "character-ir-candidate/v0.6", "truth_status": status}
            for writer, source in ((compile_reversible_gltf, self.gltf), (compile_reversible_glb, self.source)):
                with self.subTest(status=status, writer=writer.__name__):
                    with self.assertRaisesRegex(ValueError, "refusing to embed truth_status"):
                        writer(source, ir)

    def test_existing_candidate_carrier_cannot_claim_canonical_authority(self):
        ir = {"schema": "character-ir-candidate/v0.6", "truth_status": "candidate"}
        carrier = {**self.gltf, "extras": {EXTENSION_KEY: {
            "version": "0.2.0", "encoding": "json", "digest": ir_digest(ir),
            "character_ir": ir, "truth_class": "embedded_canonical_ir"}}}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy-candidate.gltf"
            path.write_text(json.dumps(carrier))
            with self.assertRaisesRegex(ValueError, "candidate"):
                audit_asset(path)

    def test_missing_digest_cannot_be_reported_as_verified(self):
        carrier = compile_reversible_gltf(self.gltf, {"schema": "character-ir/v0.6", "parts": []})
        for value in (None, "", False):
            invalid = copy.deepcopy(carrier)
            invalid["extras"][EXTENSION_KEY]["digest"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "digest"):
                    recover_embedded_ir(invalid)

    def test_valid_legacy_ir_remains_reversible_without_mutating_input(self):
        ir = {"schema": "character-ir/v0.6", "parts": [{"id": "head"}], "unresolved": ["back"]}
        before = copy.deepcopy(self.gltf)
        carrier = compile_reversible_gltf(self.gltf, ir)
        self.assertEqual(recover_embedded_ir(carrier), ir)
        self.assertEqual(self.gltf, before)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "valid.gltf"
            path.write_text(json.dumps(carrier))
            self.assertTrue(score_roundtrip(ir, extract_ir(path))["canonical_exact"])


if __name__ == "__main__":
    unittest.main()
