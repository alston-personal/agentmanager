import unittest

from agentos_node.production_parity import CAPABILITY, RECEIPT_SCHEMA, inspect_request


class FakeRunner:
    def __init__(self, *, sha="abc", branch="main", service="active"):
        self.sha = sha
        self.branch = branch
        self.service = service

    def __call__(self, argv, **kwargs):
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return {"ok": bool(self.sha), "returncode": 0 if self.sha else 1, "stdout": self.sha, "stderr": ""}
        if argv[:3] == ["git", "branch", "--show-current"]:
            return {"ok": True, "returncode": 0, "stdout": self.branch, "stderr": ""}
        if argv[:2] == ["systemctl", "is-active"]:
            return {"ok": self.service == "active", "returncode": 0 if self.service == "active" else 3, "stdout": self.service, "stderr": ""}
        raise AssertionError(argv)


def request(expected="abc"):
    return {
        "schema": "agentos.execution-request/v1",
        "request_id": "req-1",
        "project_id": "leopardcat-tarot",
        "source_ref": "main",
        "source_sha": expected,
        "capability": CAPABILITY,
        "environment": "production",
        "parameters": {
            "repo_path": "/srv/leopardcat",
            "service": "leopardcat-tarot.service",
            "listen_port": 8088,
            "public_url": "https://leopardcat-tarot.milkcat.org",
            "health_path": "/api/stats",
        },
    }


class ProductionParityReceiptTest(unittest.TestCase):
    def test_matching_runtime_is_authoritative(self):
        probes = iter([{"ok": True, "status": 200}, {"ok": True, "status": 200}])
        receipt = inspect_request(request(), runner=FakeRunner(), http_probe=lambda *_a, **_k: next(probes))
        self.assertEqual(receipt["schema"], RECEIPT_SCHEMA)
        self.assertEqual(receipt["parity"], "matched")
        self.assertFalse(receipt["authority"]["sandbox_fallback_allowed"])
        self.assertEqual(receipt["observed"]["git_sha"], "abc")

    def test_sha_mismatch_is_mismatch_when_runtime_reachable(self):
        probes = iter([{"ok": True, "status": 200}, {"ok": True, "status": 200}])
        receipt = inspect_request(request("wanted"), runner=FakeRunner(sha="actual"), http_probe=lambda *_a, **_k: next(probes))
        self.assertEqual(receipt["parity"], "mismatch")

    def test_inactive_service_is_unavailable(self):
        probes = iter([{"ok": False, "error": "transport_error"}, {"ok": True, "status": 200}])
        receipt = inspect_request(request(), runner=FakeRunner(service="inactive"), http_probe=lambda *_a, **_k: next(probes))
        self.assertEqual(receipt["parity"], "unavailable")
        self.assertFalse(receipt["observed"]["service"]["active"])

    def test_oracle_dns_failure_is_preserved_not_retried_elsewhere(self):
        probes = iter([{"ok": True, "status": 200}, {"ok": False, "error": "dns_error", "detail": "name lookup failed"}])
        receipt = inspect_request(request(), runner=FakeRunner(), http_probe=lambda *_a, **_k: next(probes))
        self.assertEqual(receipt["parity"], "unavailable")
        self.assertEqual(receipt["observed"]["public_probe"]["error"], "dns_error")
        self.assertFalse(receipt["authority"]["sandbox_fallback_allowed"])

    def test_local_failure_is_distinct_from_public_dns_failure(self):
        probes = iter([{"ok": False, "error": "transport_error"}, {"ok": False, "error": "dns_error"}])
        receipt = inspect_request(request(), runner=FakeRunner(), http_probe=lambda *_a, **_k: next(probes))
        self.assertEqual(receipt["observed"]["local_probe"]["error"], "transport_error")
        self.assertEqual(receipt["observed"]["public_probe"]["error"], "dns_error")

    def test_rejects_wrong_schema_or_capability(self):
        bad = request()
        bad["schema"] = "wrong"
        with self.assertRaises(ValueError):
            inspect_request(bad)
        bad = request()
        bad["capability"] = "something.else"
        with self.assertRaises(ValueError):
            inspect_request(bad)


if __name__ == "__main__":
    unittest.main()
