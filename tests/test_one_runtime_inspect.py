from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentos_node.one_mcp_stdio import _runtime_inspect
from agentos_node.one_runtime_inspect import FIXED_SERVICES, inspect_oracle_runtime


class FakeClientGateway:
    mode = "client"


class FakeOracleGateway:
    mode = "oracle-local"

    def __init__(self, data_root: Path, core_node_id: str = "oracle-core-node"):
        self.data_root = data_root
        self.core_node_id = core_node_id


class OneRuntimeInspectTests(unittest.TestCase):
    def _write_realm(self, root: Path, capabilities: list[str]) -> None:
        realm = root / "realm"
        realm.mkdir(parents=True)
        (realm / "fabric.json").write_text('{"realm_id":"realm-alston"}\n', encoding="utf-8")
        (realm / "nodes.json").write_text(
            json.dumps(
                {
                    "schema": "agentos.node-registry/v0.1",
                    "realm_id": "realm-alston",
                    "nodes": {
                        "oracle-core-node": {
                            "node_id": "oracle-core-node",
                            "status": "online",
                            "last_heartbeat_at": "2026-09-03T00:39:12Z",
                            "capabilities": capabilities,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_client_mode_is_not_a_remote_shell_backdoor(self):
        result = _runtime_inspect(FakeClientGateway())
        self.assertFalse(result["supported"])
        self.assertEqual(result["reason"], "oracle_local_only")
        self.assertFalse(result["mutation_allowed"])
        self.assertFalse(result["credential_exposed"])

    def test_projection_is_fixed_and_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-data"
            self._write_realm(root, ["agentos.one.resolve", "agent.employee.wake.deliver"])
            core = Path(tmp) / "private-core-path"
            legacy = Path(tmp) / "private-legacy-path"
            (core / ".git").mkdir(parents=True)
            (legacy / ".git").mkdir(parents=True)

            def fake_run(argv, **kwargs):
                class Result:
                    returncode = 0
                    stdout = ""
                result = Result()
                if argv[0] == "git":
                    if "rev-parse" in argv:
                        result.stdout = "a" * 40 + "\n"
                    elif "branch" in argv:
                        result.stdout = "core/integration\n"
                    elif "status" in argv:
                        result.stdout = ""
                elif argv[0] == "systemctl":
                    result.stdout = "active\n"
                return result

            with mock.patch("agentos_node.one_runtime_inspect.subprocess.run", side_effect=fake_run):
                result = inspect_oracle_runtime(
                    data_root=root,
                    core_repo_root=core,
                    legacy_repo_root=legacy,
                    core_node_id="oracle-core-node",
                )

            serialized = json.dumps(result)
            self.assertEqual(result["schema"], "agentos.one-runtime-inspect/v0.1")
            self.assertFalse(result["mutation_allowed"])
            self.assertFalse(result["credential_exposed"])
            self.assertEqual(set(result["services"]), set(FIXED_SERVICES))
            self.assertTrue(result["realm"]["core_node"]["employee_wake_capable"])
            self.assertNotIn(str(core), serialized)
            self.assertNotIn(str(legacy), serialized)
            self.assertNotIn("ExecStart", serialized)
            self.assertNotIn("Environment", serialized)

    def test_missing_wake_capability_is_visible_without_mutating_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-data"
            self._write_realm(root, ["agentos.one.resolve"])
            with mock.patch("agentos_node.one_runtime_inspect._git_projection", return_value={"present": False, "head_sha": None, "branch": None, "dirty_tracked": None}), mock.patch("agentos_node.one_runtime_inspect._service_state", return_value="missing"):
                result = inspect_oracle_runtime(data_root=root)
            self.assertFalse(result["realm"]["core_node"]["employee_wake_capable"])
            self.assertEqual(result["services"]["core_supervisor"], "missing")
            self.assertEqual(result["services"]["employee_worker_host"], "missing")

    def test_oracle_stdio_adapter_uses_gateway_data_root_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "agent-data"
            self._write_realm(root, [])
            gateway = FakeOracleGateway(root)
            with mock.patch("agentos_node.one_mcp_stdio.inspect_oracle_runtime", return_value={"schema": "agentos.one-runtime-inspect/v0.1", "mutation_allowed": False, "credential_exposed": False}) as inspect:
                result = _runtime_inspect(gateway)
            inspect.assert_called_once_with(data_root=root, core_node_id="oracle-core-node")
            self.assertEqual(result["schema"], "agentos.one-runtime-inspect/v0.1")


if __name__ == "__main__":
    unittest.main()
