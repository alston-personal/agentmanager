from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/windows/recovery_one_probe.py"
spec = importlib.util.spec_from_file_location("recovery_one_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def config(realm_id="realm-alston"):
    return {
        "one_url": "https://agentos.milkcat.org",
        "realm_id": realm_id, "node_id": "windows-node",
        "node_token": "a" * 32,
    }


class FakeResponse:
    status = 200

    def __init__(self, content=b'{"schema":"agentos.node-bootstrap/v0.1"}'):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.content[:n]


class RecoveryProbeTests(unittest.TestCase):
    def test_authenticated_independent_bootstrap_round_trip(self):
        calls = []
        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse()
        result = probe.probe_one(config(), opener=opener)
        req, timeout = calls[0]
        self.assertEqual(timeout, 8)
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url,
                         "https://agentos.milkcat.org/v1/bootstrap?node_id=windows-node")
        self.assertEqual(req.get_header("Authorization"), "Bearer " + "a"*32)
        self.assertTrue(result["one_transport_roundtrip"])
        self.assertFalse(result["adapter_download_verified"])
        self.assertFalse(result["recovery_update_authorized"])
        self.assertNotIn("node_token", result)

    def test_tenant_realm_has_explicit_scoped_endpoint(self):
        realm = "realm-u-" + "a"*24
        self.assertEqual(probe.bootstrap_url(config(realm)),
                         "https://agentos.milkcat.org/v1/realms/" + realm +
                         "/bootstrap?node_id=windows-node")

    def test_existing_studio_one_gateway_legacy_bootstrap(self):
        conf = {**config(), "one_url": "https://studio.milkcat.org/dashboard/api/agentos"}
        self.assertEqual(probe.bootstrap_url(conf),
                         "https://studio.milkcat.org/dashboard/api/agentos/v1/bootstrap?node_id=windows-node")
        tenant = {**conf, "realm_id": "realm-u-" + "a"*24}
        with self.assertRaises(ValueError):
            probe.bootstrap_url(tenant)

    def test_origin_and_identity_fail_closed(self):
        invalid = [
            {**config(), "one_url": "http://agentos.milkcat.org"},
            {**config(), "one_url": "https://evil.test"},
            {**config(), "one_url": "https://agentos.milkcat.org@evil.test"},
            {**config(), "one_url": "https://agentos.milkcat.org/v1/health"},
            {**config(), "node_id": "../other"},
            {**config(), "node_token": "weak"},
            {**config(), "node_token": "x"*20 + " "},
            {**config(), "realm_id": "../../other"},
        ]
        for item in invalid:
            with self.subTest(item={k:v for k,v in item.items() if k != "node_token"}):
                with self.assertRaises(ValueError):
                    probe.validate_config(item)

    def test_no_remote_code_execution_and_reject_oversize(self):
        result = probe.probe_one(config(), opener=lambda *_args, **_kw:
                                 FakeResponse(b'{"schema":"agentos.node-bootstrap/v0.1","install":"run-me"}'))
        self.assertTrue(result["one_transport_roundtrip"])
        self.assertNotIn("install", result)
        with self.assertRaises(ValueError):
            probe.probe_one(config(), opener=lambda *_args, **_kw:
                            FakeResponse(b"X" * 131073))

    def test_bootstrap_schema_and_identity_must_match(self):
        for payload in (
            b'{"schema":"wrong"}',
            b'{"schema":"agentos.node-bootstrap/v0.1","node_id":"other"}',
            b'{"schema":"agentos.node-bootstrap/v0.1","realm_id":"other"}',
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                probe.probe_one(config(), opener=lambda *_a, **_k: FakeResponse(payload))

    def test_recovery_probe_disallows_http_redirects(self):
        import urllib.request
        handler = probe.NoRecoveryRedirect()
        req = urllib.request.Request("https://agentos.milkcat.org/v1/bootstrap",
                                     headers={"Authorization":"Bearer secret"})
        with self.assertRaises(RuntimeError):
            handler.redirect_request(req, None, 302, "Moved",
                                     {}, "https://evil.example/steal")

    def test_atomic_status_write_keeps_secrets_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recovery" / "probe.json"
            result = probe.probe_one(config(),
                                     opener=lambda *_a, **_k: FakeResponse())
            probe.write_status(path, result)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["schema"], probe.RESULT_SCHEMA)
            self.assertFalse(saved["recovery_update_authorized"])
            self.assertNotIn("a"*32, path.read_text())

    def test_probe_never_imports_normal_runtime(self):
        text = SCRIPT.read_text()
        self.assertNotIn("from agentos_node", text)
        self.assertNotIn("from agent_core", text)


if __name__ == "__main__":
    unittest.main()
