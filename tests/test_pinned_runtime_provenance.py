"""Regression tests for runtime provenance tied to the actually loaded snapshot."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy

SCHEMA = "agentos.thin-client-runtime/v0.1"
SHA = "a" * 40


class PinnedProvenanceTests(unittest.TestCase):
    def _manifest(self, module_file, generic):
        client = ThinClient(NodeIdentity("realm-test", "oracle-exec"), ThinClientPolicy())
        with patch("agentos_node.thin_client.__file__", str(module_file)), \
             patch("agentos_node.thin_client.observe_runtime", return_value=generic), \
             patch("agentos_node.executor_reconcile.discover_executor_inventory", return_value={}):
            return client.capability_manifest()["runtime"]

    def test_pinned_snapshot_overrides_generic_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "runtime" / SHA
            module = root / "agentos_node" / "thin_client.py"
            module.parent.mkdir(parents=True)
            (root / "runtime-provenance.json").write_text(json.dumps({
                "schema": SCHEMA, "status": "observed", "source_commit": SHA,
            }))
            actual = self._manifest(module, {
                "schema": SCHEMA, "status": "observed", "source_commit": "b" * 40,
            })
            self.assertEqual(actual["source_commit"], SHA)
            self.assertEqual(actual["status"], "observed")

    def test_bad_pinned_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "runtime" / SHA
            module = root / "agentos_node" / "thin_client.py"
            module.parent.mkdir(parents=True)
            (root / "runtime-provenance.json").write_text(json.dumps({
                "schema": SCHEMA, "status": "observed", "source_commit": "b" * 40,
            }))
            actual = self._manifest(module, {
                "schema": SCHEMA, "status": "observed", "source_commit": SHA,
            })
            self.assertEqual(actual["status"], "invalid")
            self.assertEqual(actual["source_commit"], "")

    def test_missing_pinned_metadata_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as td:
            module = Path(td) / "runtime" / SHA / "agentos_node" / "thin_client.py"
            module.parent.mkdir(parents=True)
            actual = self._manifest(module, {
                "schema": SCHEMA, "status": "environment", "source_commit": SHA,
            })
            self.assertEqual(actual["status"], "invalid")
            self.assertEqual(actual["source_commit"], "")

    def test_unpinned_installation_preserves_generic_observer(self):
        with tempfile.TemporaryDirectory() as td:
            module = Path(td) / "agentos_node" / "thin_client.py"
            module.parent.mkdir(parents=True)
            generic = {"schema": SCHEMA, "status": "observed", "source_commit": "b" * 40}
            self.assertEqual(self._manifest(module, generic), generic)


if __name__ == "__main__":
    unittest.main()
