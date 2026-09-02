from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_core.core_supervisor_daemon import (
    _delivery_mode,
    _heartbeat_step,
    _process_singleton_lock,
    _require_existing_one_root,
    build_service,
    main,
    run_persistent,
)
from agent_core.employee_runtime import EmployeeRuntime


class _Receipt:
    next_poll_seconds = 60


class _FakeService:
    def __init__(self):
        self.claims = 0
        self.cycles = 0
        self.heartbeats = 0

    class _Leader:
        generation = 1

    def claim_leader(self, *, lease_seconds):
        self.claims += 1
        return self._Leader()

    def run_cycle(self, generation):
        self.cycles += 1
        return _Receipt()

    def heartbeat_leader(self, generation, *, lease_seconds):
        self.heartbeats += 1
        return self._Leader()


class _StopAfterWaits:
    def __init__(self, stop_after: int):
        self.stop_after = stop_after
        self.waits: list[int] = []

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waits.append(int(seconds))
        return len(self.waits) >= self.stop_after


class CoreSupervisorDaemonTests(unittest.TestCase):
    def _write_one_root(self, root: Path, *, fabric_realm="realm-test", node_realm="realm-test"):
        realm = root / "realm"
        realm.mkdir(parents=True, exist_ok=True)
        (realm / "fabric.json").write_text(
            json.dumps({
                "schema": "agentos.realm-fabric/v0.1",
                "realm_id": fabric_realm,
                "invites": {},
                "join_requests": {},
                "nodes": {},
                "tasks": {},
                "receipts": {},
            }),
            encoding="utf-8",
        )
        (realm / "nodes.json").write_text(
            json.dumps({
                "schema": "agentos.node-registry/v0.1",
                "realm_id": node_realm,
                "nodes": {},
            }),
            encoding="utf-8",
        )

    def test_heartbeat_step_never_sleeps_past_half_leader_lease(self):
        self.assertEqual(_heartbeat_step(60, 30), 15)
        self.assertEqual(_heartbeat_step(10, 30), 10)
        self.assertEqual(_heartbeat_step(1, 5), 1)

    def test_long_idle_backoff_heartbeats_before_leader_can_expire(self):
        service = _FakeService()
        stop = _StopAfterWaits(stop_after=3)
        run_persistent(service, stop_event=stop, leader_lease_seconds=30)
        self.assertEqual(service.claims, 1)
        self.assertEqual(service.cycles, 1)
        self.assertEqual(stop.waits, [15, 15, 15])
        self.assertEqual(service.heartbeats, 2)

    def test_process_lock_is_held_for_daemon_lifetime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with _process_singleton_lock(root):
                with self.assertRaisesRegex(RuntimeError, "supervisor_process_already_active"):
                    with _process_singleton_lock(root):
                        self.fail("second daemon lock must not be acquired")
            with _process_singleton_lock(root):
                pass

    def test_health_cli_is_read_only_and_does_not_claim_leader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(["--runtime-root", str(root), "--health"])
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "inactive")
            self.assertFalse(payload["dispatch_performed"])
            self.assertFalse((root / "supervisor" / "leader.json").exists())

    def test_once_cli_journals_pending_work_without_dispatch_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            runtime = EmployeeRuntime(root)
            runtime.create_employee("steward", "Steward", role_ids=["governance.spec_steward"])
            runtime.create_assignment("audit-1", "steward", "Audit one issue")

            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(["--runtime-root", str(root), "--service-id", "test-supervisor", "--once"])
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["new_intent_count"], 1)
            self.assertFalse(payload["dispatch_performed"])
            self.assertEqual(payload["authority_boundary"], "persistent_observe_plan_only")
            intent_files = list((root / "supervisor" / "intents").glob("reconcile_*.json"))
            self.assertEqual(len(intent_files), 1)

    def test_runtime_root_must_be_explicit_absolute_path(self):
        with self.assertRaisesRegex(ValueError, "employee_runtime_root_must_be_absolute"):
            main(["--runtime-root", "relative/path", "--health"])

    def test_delivery_mode_is_explicit_and_fail_closed(self):
        self.assertEqual(_delivery_mode("disabled"), "disabled")
        self.assertEqual(_delivery_mode("one_direct"), "one_direct")
        with self.assertRaisesRegex(ValueError, "invalid_supervisor_delivery_mode"):
            _delivery_mode("github_actions")
        with self.assertRaisesRegex(ValueError, "invalid_supervisor_delivery_mode"):
            _delivery_mode("auto")

    def test_default_builder_does_not_attach_delivery_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            service = build_service(
                runtime_root=root / "employee-runtime",
                service_id="test-supervisor",
                base_poll_seconds=2,
                max_poll_seconds=16,
            )
            self.assertIsNone(service.delivery_driver)

    def test_one_direct_builder_requires_existing_matching_one_realm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            runtime_root = root / "employee-runtime"
            one_root = root / "one"
            with self.assertRaisesRegex(RuntimeError, "supervisor_one_control_plane_state_missing"):
                build_service(
                    runtime_root=runtime_root,
                    service_id="test-supervisor",
                    base_poll_seconds=2,
                    max_poll_seconds=16,
                    delivery_mode="one_direct",
                    one_data_root=one_root,
                )
            self.assertFalse((one_root / "realm" / "fabric.json").exists())
            self.assertFalse((one_root / "realm" / "nodes.json").exists())

            self._write_one_root(one_root, fabric_realm="realm-a", node_realm="realm-b")
            with self.assertRaisesRegex(RuntimeError, "supervisor_one_control_plane_realm_mismatch"):
                _require_existing_one_root(one_root)

    def test_one_direct_builder_attaches_only_to_existing_matching_realm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            runtime_root = root / "employee-runtime"
            one_root = root / "one"
            self._write_one_root(one_root)
            service = build_service(
                runtime_root=runtime_root,
                service_id="test-supervisor",
                base_poll_seconds=2,
                max_poll_seconds=16,
                delivery_mode="one_direct",
                one_data_root=one_root,
            )
            self.assertIsNotNone(service.delivery_driver)
            self.assertEqual(service.delivery_driver.authority.requested_transport, "one_direct")
            self.assertEqual(_require_existing_one_root(one_root), "realm-test")


if __name__ == "__main__":
    unittest.main()
