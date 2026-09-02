from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.employee_worker_host import (
    CAPSULE_FIELDS,
    DISPATCH_SCHEMA,
    EmployeeWorkerAdapterRegistry,
    EmployeeWorkerHost,
    WorkerHostCandidate,
)
from agentos_node.employee_worker_host_runtime import ExactEmployeeWorkerHost


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "governance" / "employee-worker-adapters.json"


def _capsule(*, wake_id: str = "wake-1", presence_generation: int = 1) -> dict:
    intent = {
        "schema": "agentos.employee-wake-intent/v1",
        "wake_id": wake_id,
        "employee_id": "agentos-spec-steward",
        "assignment_id": "spec-steward-o3-acceptance-v1",
        "mode": "fresh",
        "expected_lease_generation": 1,
        "goal": "bounded acceptance",
        "thread_head": "o3:seed",
        "constraints": ["read-only"],
        "role_ids": ["governance.spec_steward"],
        "skill_ids": ["spec.audit"],
        "resume_required": False,
        "prior_execution_state": "not_started",
        "authority_boundary": "selection_only_no_execution",
        "executor_selection": "unbound",
        "transport_selection": "unbound",
        "credential_exposed": False,
    }
    route = {
        "schema": "agentos.employee-wake-route/v1",
        "employee_id": "agentos-spec-steward",
        "node_id": "oracle-core",
        "presence_id": "presence-1",
        "presence_generation": presence_generation,
    }
    payload = {
        "schema": "agentos.employee-wake-delivery/v1",
        "wake_id": wake_id,
        "employee_id": "agentos-spec-steward",
        "assignment_id": "spec-steward-o3-acceptance-v1",
        "node_id": "oracle-core",
        "presence_id": "presence-1",
        "presence_generation": presence_generation,
        "expected_lease_generation": 1,
        "digest": "digest-1",
        "wake_intent": intent,
        "employee_wake_route": route,
    }
    assert set(payload) == CAPSULE_FIELDS
    return payload


class EmployeeWorkerHostTests(unittest.TestCase):
    def _host(self, base: Path) -> ExactEmployeeWorkerHost:
        return ExactEmployeeWorkerHost(
            runtime_root=base / "runtime",
            wake_root=base / "wake",
            host_state_root=base / "host",
            worker_state_root=base / "worker",
            node_id="oracle-core",
            adapter_registry_path=REGISTRY,
        )

    def test_registry_is_source_controlled_and_contains_no_execution_strings(self):
        payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
        text = json.dumps(payload).casefold()
        for forbidden in ("executable", "argv", "command", "module", "url", "token", "secret", "credential"):
            self.assertNotIn(forbidden, text)
        registry = EmployeeWorkerAdapterRegistry(REGISTRY)
        projection = registry.projection()
        self.assertEqual(projection[0]["runner_kind"], "spec_steward_o3")

    def test_child_environment_drops_host_credentials(self):
        with patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "ghp_should_not_leak",
                "AGENTOS_NODE_TOKEN": "node-secret",
                "ONE_TOKEN": "one-secret",
                "PATH": "/untrusted/bin",
                "LANG": "C.UTF-8",
            },
            clear=False,
        ):
            env = EmployeeWorkerHost._child_environment()
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("AGENTOS_NODE_TOKEN", env)
        self.assertNotIn("ONE_TOKEN", env)
        self.assertNotEqual(env.get("PATH"), "/untrusted/bin")
        self.assertEqual(env.get("LANG"), "C.UTF-8")

    def test_exact_runtime_appends_exact_wake_selector(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            host = self._host(base)
            capsule = _capsule(wake_id="wake-exact", presence_generation=7)
            adapter = host.registry.resolve(capsule)
            self.assertIsNotNone(adapter)
            host._pinned_candidate = WorkerHostCandidate(
                path=base / "wake" / "agentos-spec-steward" / "wake-exact.000007.json",
                capsule=capsule,
                adapter=adapter,
            )
            command = host._child_command(adapter)
            self.assertIn("--wake-id", command)
            self.assertEqual(command[command.index("--wake-id") + 1], "wake-exact")
            self.assertEqual(command[command.index("--presence-generation") + 1], "7")
            self.assertNotIn("--executable", command)
            self.assertNotIn("--argv", command)

    def test_prior_launch_is_unknown_and_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            host = self._host(base)
            capsule = _capsule()
            wake_path = base / "wake" / capsule["employee_id"] / "wake-1.000001.json"
            wake_path.parent.mkdir(parents=True, exist_ok=True)
            wake_path.write_text(json.dumps(capsule), encoding="utf-8")
            dispatch_path = base / "host" / "dispatches" / capsule["employee_id"] / "wake-1.000001.json"
            dispatch_path.parent.mkdir(parents=True, exist_ok=True)
            dispatch_path.write_text(
                json.dumps(
                    {
                        "schema": DISPATCH_SCHEMA,
                        "status": "launching",
                        "wake_id": "wake-1",
                    }
                ),
                encoding="utf-8",
            )
            with patch("agentos_node.employee_worker_host.subprocess.run") as run:
                result = host.process_one()
            run.assert_not_called()
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["error_code"], "employee_worker_prior_launch_unknown")

    def test_untrusted_child_result_becomes_unknown_without_raw_output(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            host = self._host(base)
            capsule = _capsule()
            wake_path = base / "wake" / capsule["employee_id"] / "wake-1.000001.json"
            wake_path.parent.mkdir(parents=True, exist_ok=True)
            wake_path.write_text(json.dumps(capsule), encoding="utf-8")
            completed = type("Completed", (), {"returncode": 0, "stdout": "Bearer super-secret\n"})()
            with patch("agentos_node.employee_worker_host.subprocess.run", return_value=completed):
                result = host.process_one()
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["error_code"], "employee_worker_child_result_untrusted")
            self.assertNotIn("Bearer", json.dumps(result))
            self.assertIsNone(result["child_result"])


if __name__ == "__main__":
    unittest.main()
