import json
import os
import tempfile
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
        self.assertEqual(status["mode"], one_mcp.CLIENT_MODE)
        self.assertNotIn("TOPSECRET", json.dumps(status))
        self.assertIsNone(seen[0].headers.get("Authorization"))
        self.assertEqual(
            seen[1].headers.get("Authorization"),
            "Bearer TOPSECRET",
        )

    def test_oracle_local_status_uses_node_registry_projection_without_token(self):
        gateway = one_mcp.OracleLocalGateway(
            data_root=Path("/tmp/agent-data-test"),
            core_node_id="oracle-core-node",
        )
        node_map = {
            "schema": "agentos.node-map/v0.1",
            "realm_id": "realm-alston",
            "node_count": 2,
            "realm_capabilities": ["agentos.one.resolve"],
            "nodes": [
                {
                    "node_id": "oracle-core-node",
                    "role": "core",
                    "status": "online",
                    "capabilities": ["agentos.one.resolve"],
                    "surface_inventory": {"surfaces": []},
                },
                {
                    "node_id": "client-a",
                    "role": "client",
                    "status": "online",
                    "capabilities": ["filesystem.read"],
                    "surface_inventory": {
                        "surfaces": [{"provider": "antigravity"}]
                    },
                },
            ],
        }
        with mock.patch.object(
            gateway, "_node_map", return_value=node_map
        ):
            status = gateway.status()
            bootstrap = gateway.bootstrap()

        self.assertTrue(status["connected"])
        self.assertEqual(status["mode"], one_mcp.ORACLE_LOCAL_MODE)
        self.assertEqual(status["surface"], "antigravity")
        self.assertEqual(
            status["executor_class"], "antigravity-gemini"
        )
        self.assertFalse(status["credential_exposed"])
        self.assertEqual(
            bootstrap["schema"],
            "agentos.one-local-bootstrap/v0.1",
        )
        self.assertEqual(
            bootstrap["inherited_surface_providers"],
            ["antigravity"],
        )

    def test_gateway_mode_selects_oracle_local_when_no_client_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "realm").mkdir()
            (root / "realm" / "nodes.json").write_text(
                "{}",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"AGENT_DATA_ROOT": str(root)},
                clear=True,
            ), mock.patch.object(
                one_mcp,
                "discover_client_config",
                side_effect=FileNotFoundError,
            ), mock.patch.object(one_mcp.os, "name", "posix"):
                self.assertEqual(
                    one_mcp.gateway_mode(),
                    one_mcp.ORACLE_LOCAL_MODE,
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
