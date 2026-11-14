"""Capability marker provenance must match the installer, not grant new actions."""
import unittest

from agentos_node.runtime_converge_action_relay import capability_marker_payload

SHA = "a" * 40


class ActionRelayMarkerProvenanceTest(unittest.TestCase):
    def test_canonical_main_publishes_existing_bounded_capabilities(self):
        marker = capability_marker_payload(source_ref="main", source_commit=SHA)
        self.assertEqual(marker["schema"], "agentos.action-relay-capabilities/v1")
        self.assertEqual(marker["source_ref"], "main")
        self.assertEqual(marker["source_commit"], SHA)
        self.assertIn("agentos.executor.job", marker["actions"])
        self.assertIn("node.runtime.converge", marker["node_capabilities"])

    def test_existing_legacy_installer_source_is_unchanged(self):
        marker = capability_marker_payload(source_ref="core/integration", source_commit=SHA)
        self.assertEqual(marker["source_ref"], "core/integration")

    def test_existing_feature_readiness_source_is_preserved(self):
        marker = capability_marker_payload(
            source_ref="feature/realm-node-fabric-readiness", source_commit=SHA)
        self.assertEqual(marker["source_ref"], "feature/realm-node-fabric-readiness")

    def test_unrecognized_refs_rejected(self):
        for ref in ("", "old-main", "refs/heads/main", "origin/main", "../main"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "provenance"):
                capability_marker_payload(source_ref=ref, source_commit=SHA)

    def test_noncanonical_commit_id_rejected(self):
        for sha in ("", "A" * 40, "deadbeef", "g" * 40, "a" * 41):
            with self.subTest(sha=sha), self.assertRaisesRegex(ValueError, "provenance"):
                capability_marker_payload(source_ref="main", source_commit=sha)


if __name__ == "__main__":
    unittest.main()
