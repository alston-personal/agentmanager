from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agent_core import spec_steward_presence_cli as cli
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.spec_steward_bootstrap import ensure_spec_steward


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SpecStewardPresenceCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.runtime_root = base / "runtime"
        self.one_root = base / "one"
        ensure_spec_steward(EmployeeRuntime(self.runtime_root))
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _write(
            self.one_root / "realm" / "fabric.json",
            {"schema": "agentos.realm-fabric/v0.1", "realm_id": "realm-o3"},
        )
        _write(
            self.one_root / "realm" / "nodes.json",
            {
                "schema": "agentos.node-registry/v0.1",
                "realm_id": "realm-o3",
                "nodes": {
                    "node-o3": {
                        "node_id": "node-o3",
                        "role": "client",
                        "hostname": "o3-test",
                        "platform": "linux",
                        "platform_release": "test",
                        "capabilities": [WAKE_CAPABILITY],
                        "tool_presence": {},
                        "surface_inventory": {},
                        "runtime": {},
                        "workspace_roots": {},
                        "status": "online",
                        "first_seen_at": now,
                        "last_manifest_at": now,
                        "last_heartbeat_at": now,
                        "benchmark": None,
                    }
                },
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, command: str, *extra: str) -> list[str]:
        return [
            "--runtime-root", str(self.runtime_root),
            "--one-data-root", str(self.one_root),
            "--node-id", "node-o3",
            command,
            *extra,
        ]

    def test_cli_has_no_arbitrary_employee_or_node_registration_surface(self):
        parser = cli.build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertNotIn("--employee-id", option_strings)
        self.assertNotIn("--capability", option_strings)
        self.assertNotIn("--register-node", option_strings)
        self.assertNotIn("--create-realm", option_strings)

    def test_bind_requires_existing_online_wake_capable_node(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cli.main(self._args("bind", "--presence-id", "presence-o3", "--ttl-seconds", "300"))
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["employee_id"], "agentos-spec-steward")
        self.assertEqual(payload["node_id"], "node-o3")
        self.assertEqual(payload["required_capability"], WAKE_CAPABILITY)
        self.assertFalse(payload["executor_identity_bound"])
        self.assertFalse(payload["credential_exposed"])

    def test_bind_fails_if_node_lacks_wake_capability(self):
        nodes_path = self.one_root / "realm" / "nodes.json"
        nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
        nodes["nodes"]["node-o3"]["capabilities"] = []
        _write(nodes_path, nodes)
        with self.assertRaisesRegex(PermissionError, "lacks_wake_capability"):
            cli.main(self._args("bind", "--presence-id", "presence-o3"))
        self.assertFalse(
            (self.runtime_root / "realm" / "employee-presence" / "agentos-spec-steward.json").exists()
        )

    def test_missing_one_state_fails_without_initializing_shadow_realm(self):
        (self.one_root / "realm" / "fabric.json").unlink()
        (self.one_root / "realm" / "nodes.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "one_control_plane_state_missing"):
            cli.main(self._args("bind", "--presence-id", "presence-o3"))
        self.assertFalse((self.one_root / "realm" / "fabric.json").exists())
        self.assertFalse((self.one_root / "realm" / "nodes.json").exists())

    def test_inspect_does_not_bind_absent_presence(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = cli.main(self._args("inspect"))
        self.assertEqual(code, 3)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "absent")
        self.assertFalse(
            (self.runtime_root / "realm" / "employee-presence" / "agentos-spec-steward.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
