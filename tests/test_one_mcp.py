import io
import json
import os
import tempfile
import unittest
import urllib.error
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

    def test_http_error_body_is_never_exposed(self):
        cfg = one_mcp.ClientConfig(
            "http://one",
            "realm-test",
            "node-test",
            "TOPSECRET",
        )
        body = io.BytesIO(
            b'{"node_token":"TOPSECRET","secret":"SERVERSECRET","path":"/private/path"}'
        )
        error = urllib.error.HTTPError(
            "http://one/v1/bootstrap",
            401,
            "Unauthorized",
            {},
            body,
        )
        with mock.patch.object(
            one_mcp.urllib.request,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaises(one_mcp.OneGatewayError) as ctx:
                one_mcp.OneGateway(cfg).bootstrap()
        text = str(ctx.exception)
        self.assertEqual(text, "one_http_401")
        self.assertNotIn("TOPSECRET", text)
        self.assertNotIn("SERVERSECRET", text)
        self.assertNotIn("/private/path", text)

    def test_client_bootstrap_projects_executor_safe_fields_only(self):
        cfg = one_mcp.ClientConfig(
            "http://one",
            "realm-test",
            "node-test",
            "TOPSECRET",
        )
        payload = {
            "ok": True,
            "schema": "agentos.node-bootstrap/v0.1",
            "realm_id": "realm-test",
            "node_id": "node-test",
            "realm_node_count": 2,
            "realm_capabilities": ["agentos.one.resolve"],
            "node": {
                "hostname": "private-host",
                "metadata": {"path": "/home/private/work"},
            },
            "private_runtime": {"username": "private-user"},
        }
        with mock.patch.object(
            one_mcp.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            bootstrap = one_mcp.OneGateway(cfg).bootstrap()
        serialized = json.dumps(bootstrap)
        self.assertEqual(bootstrap["realm_id"], "realm-test")
        self.assertEqual(bootstrap["node_id"], "node-test")
        self.assertEqual(bootstrap["projection"], "executor-safe-readonly")
        self.assertNotIn("node", bootstrap)
        self.assertNotIn("private-host", serialized)
        self.assertNotIn("/home/private/work", serialized)
        self.assertNotIn("private-user", serialized)

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
                    "hostname": "private-oracle-host",
                    "capabilities": ["agentos.one.resolve"],
                    "surface_inventory": {"surfaces": []},
                    "metadata": {"path": "/home/ubuntu/private"},
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
        serialized = json.dumps(bootstrap)
        self.assertNotIn("node", bootstrap)
        self.assertNotIn("private-oracle-host", serialized)
        self.assertNotIn("/home/ubuntu/private", serialized)

    def test_resolve_keeps_canonical_ir_but_drops_project_source_paths(self):
        gateway = one_mcp.OracleLocalGateway(
            data_root=Path("/tmp/agent-data-test"),
            core_node_id="oracle-core-node",
        )
        raw = {
            "schema": "agentos.resolve/v1",
            "intent": "continue",
            "project": {
                "id": "agentos-core",
                "name": "AgentOS Core",
                "aliases": ["core"],
                "identity_source": "governance-directory",
                "source": {
                    "canonical_path": "/home/ubuntu/agentmanager",
                    "repo": "private/repo",
                },
                "runtime": {"username": "ubuntu"},
            },
            "mutation_allowed": False,
            "active_goal": "continue safely",
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": "idx-1",
                "active_goal": "continue safely",
                "execution_head": {"status": "active"},
                "private_path": "/secret/head",
            },
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": "idx-1",
                    "ir_id": "ir-1",
                    "goal": "continue safely",
                    "constraints": ["no secrets"],
                    "decisions": [],
                    "pending_tasks": ["next"],
                    "continuation": {"next_action": "next"},
                },
                "ir_id": "ir-1",
                "goal": "continue safely",
            },
            "node_context": {
                "schema": "agentos.one-local-bootstrap/v0.1",
                "realm_id": "realm-alston",
                "node_id": "oracle-core-node",
                "node": {"hostname": "private-host"},
            },
            "next_action": "next",
            "availability": {"continuation": True},
            "provenance": {"continuation": "project/continuity/latest.json"},
        }
        projected = one_mcp._project_resolve(raw)
        serialized = json.dumps(projected)
        self.assertEqual(
            projected["continuation"]["canonical_ir"]["ir_id"],
            "ir-1",
        )
        self.assertEqual(projected["project"]["id"], "agentos-core")
        self.assertNotIn("source", projected["project"])
        self.assertNotIn("/home/ubuntu/agentmanager", serialized)
        self.assertNotIn("/secret/head", serialized)
        self.assertNotIn("private-host", serialized)

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
