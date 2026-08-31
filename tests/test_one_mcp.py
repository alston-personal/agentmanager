import json
import os
import unittest
from pathlib import Path
from unittest import mock

from agentos_node import one_mcp


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OneMCPTests(unittest.TestCase):
    def test_localappdata_candidate(self):
        with mock.patch.dict(
            os.environ,
            {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"},
            clear=True,
        ):
            candidates = one_mcp.client_config_candidates()
        self.assertIn(
            Path(r"C:\Users\test\AppData\Local")
            / "AgentOS"
            / "state"
            / "client.json",
            candidates,
        )

    def test_status_authenticates_but_never_returns_token(self):
        cfg = one_mcp.ClientConfig(
            "http://one",
            "realm-test",
            "node-test",
            "TOPSECRET",
        )
        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request)
            if request.full_url.endswith("/v1/health"):
                return FakeResponse(
                    {"ok": True, "schema": "agentos.one-health/v0.1"}
                )
            return FakeResponse(
                {
                    "ok": True,
                    "schema": "agentos.node-bootstrap/v0.1",
                    "realm_id": "realm-test",
                    "node_id": "node-test",
                    "realm_node_count": 2,
                }
            )

        with mock.patch.object(
            one_mcp.urllib.request,
            "urlopen",
            side_effect=fake_urlopen,
        ):
            status = one_mcp.OneGateway(cfg).status()

        self.assertTrue(status["connected"])
        self.assertNotIn("TOPSECRET", json.dumps(status))
        self.assertIsNone(seen[0].headers.get("Authorization"))
        self.assertEqual(
            seen[1].headers.get("Authorization"),
            "Bearer TOPSECRET",
        )

    def test_redaction(self):
        value = one_mcp._redact(
            {
                "node_token": "x",
                "nested": {"secret": "y", "safe": 1},
            }
        )
        self.assertEqual(value["node_token"], "[REDACTED]")
        self.assertEqual(value["nested"]["secret"], "[REDACTED]")
        self.assertEqual(value["nested"]["safe"], 1)


if __name__ == "__main__":
    unittest.main()
