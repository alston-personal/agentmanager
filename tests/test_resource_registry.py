import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.resource_registry import ResourceRegistry


class _Headers:
    def get(self, key, default=None):
        return {"Server": "test-nginx", "Content-Type": "text/html"}.get(key, default)


class _Response:
    status = 200
    headers = _Headers()
    def __enter__(self): return self
    def __exit__(self, *args): return False


class TestResourceRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "registry.json"
        self.registry = ResourceRegistry(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_and_get_is_initially_unverified(self):
        self.registry.register("site://example.test", "site", {"domain": "example.test"}, ttl_seconds=60)
        entry = self.registry.describe("site://example.test")
        self.assertEqual(entry["id"], "site://example.test")
        self.assertEqual(entry["freshness"]["state"], "unverified")
        self.assertEqual(entry["verification"]["ttl_seconds"], 60)

    def test_register_preserves_observed_state(self):
        self.registry.register("site://example.test", "site", {"domain": "example.test"})
        data = self.registry.load()
        data["resources"]["site://example.test"]["observed"] = {"answer": 42}
        self.registry.save(data)
        self.registry.register("site://example.test", "site", {"domain": "example.test", "framework": "astro"})
        self.assertEqual(self.registry.get("site://example.test")["observed"]["answer"], 42)

    def test_kind_filter(self):
        self.registry.register("site://a.test", "site", {"domain": "a.test"})
        self.registry.register("service://worker", "service", {"name": "worker"})
        self.assertEqual(len(self.registry.list("site")), 1)
        self.assertEqual(self.registry.list("site")[0]["id"], "site://a.test")

    @patch("agentos_node.resource_registry.urllib.request.urlopen", return_value=_Response())
    @patch("agentos_node.resource_registry.socket.getaddrinfo", return_value=[(2,1,6,"",("203.0.113.10",443))])
    def test_targeted_site_verification_updates_observed_state(self, _dns, _http):
        self.registry.register("site://example.test", "site", {"domain": "example.test"}, ttl_seconds=3600)
        entry = self.registry.verify_site("site://example.test")
        self.assertEqual(entry["verification"]["status"], "verified")
        self.assertEqual(entry["freshness"]["state"], "fresh")
        self.assertEqual(entry["observed"]["dns"], ["203.0.113.10"])
        self.assertEqual(entry["observed"]["http"]["status"], 200)

    def test_invalid_resource_id_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.register("example.test", "site", {"domain": "example.test"})


if __name__ == "__main__":
    unittest.main()
