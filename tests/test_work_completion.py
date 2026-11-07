from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("work_completion", ROOT / "scripts" / "work_completion.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class WorkCompletionTests(unittest.TestCase):
    def path(self, temp: str) -> Path:
        return Path(temp) / "work-items.json"

    def register(self, path: Path):
        return mod.register(
            path,
            work_id="wi-1",
            project_id="agentmanager",
            title="ship feature",
            owner="role://completion.controller",
            next_action="implement code",
            acceptance=["tests pass", "production receipt exists"],
        )

    def test_active_work_requires_owner_next_action_and_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            item = self.register(path)
            self.assertEqual(item["status"], "accepted")
            errors, active = mod.audit(path)
            self.assertEqual(errors, [])
            self.assertEqual(active, ["wi-1"])

    def test_bounded_intake_registers_completion_controller_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            item = mod.register_intake_envelope(
                path,
                {
                    "schema": "agentos.work-intake/v1",
                    "work_id": "market-master-1200-mvp",
                    "project_id": "market-master-evolution",
                    "title": "Finish Market Master MVP",
                    "next_action": "Run recent-years 2454 replay with T86",
                    "acceptance": ["real replay report", "verified completion receipt"],
                    "source": "https://github.com/alston-personal/agentmanager/issues/1200",
                    "workspace": str(Path(temp) / "workspace"),
                    "lease_seconds": 600,
                },
            )
            self.assertEqual(item["owner"], "role://completion.controller")
            self.assertEqual(item["status"], "accepted")
            self.assertEqual(item["project_id"], "market-master-evolution")

    def test_bounded_intake_rejects_unknown_execution_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            with self.assertRaises(ValueError):
                mod.register_intake_envelope(
                    path,
                    {
                        "schema": "agentos.work-intake/v1",
                        "work_id": "wi-unsafe",
                        "project_id": "agentmanager",
                        "title": "unsafe",
                        "next_action": "do thing",
                        "acceptance": ["verified"],
                        "shell": "rm -rf /",
                    },
                )

    def test_done_requires_verification_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(path, work_id="wi-1", target="in_progress", actor="agent", next_action="run test")
            mod.transition(path, work_id="wi-1", target="verifying", actor="agent", next_action="verify prod")
            with self.assertRaises(ValueError):
                mod.transition(path, work_id="wi-1", target="done", actor="agent", evidence=["run 1"])
            done = mod.transition(
                path, work_id="wi-1", target="done", actor="inspector",
                evidence=["https://example.invalid/receipt"], verification="passed",
            )
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["verification"]["status"], "passed")

    def test_handoff_keeps_work_alive_and_advances_owner_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            moved = mod.handoff(
                path, work_id="wi-1", actor="chat-agent",
                new_owner="role://lobster", next_action="resume from PR 42",
            )
            self.assertEqual(moved["owner"], "role://lobster")
            self.assertEqual(moved["owner_generation"], 2)
            self.assertEqual(mod.next_item(path)["work_id"], "wi-1")

    def test_blocker_kind_is_bounded_and_safe(self):
        self.assertEqual(mod.classify_blocker("GitHub workflow still running; verify receipt"), "VERIFICATION")
        self.assertEqual(mod.classify_blocker("TWSE T86 historical data not yet available"), "MARKET_DATA")
        self.assertEqual(mod.classify_blocker("provider rate limit quota"), "PROVIDER_CAPACITY")
        self.assertEqual(mod.classify_blocker("ONE runtime converge receipt continuity"), "RUNTIME_HEALTH")
        self.assertEqual(mod.classify_blocker("human login required"), "HUMAN_AUTH")
        self.assertEqual(mod.classify_blocker("BLOCKED: executor_exception:RuntimeError"), "RUNTIME_HEALTH")
        self.assertEqual(mod.classify_blocker("任務逾時（300s）"), "PROVIDER_CAPACITY")
        self.assertEqual(mod.classify_blocker("連續 3 次驗證失敗"), "VERIFICATION")
        self.assertEqual(mod.classify_blocker("opaque domain-specific blocker"), "UNKNOWN")
        self.assertEqual(mod.classify_blocker(""), "NONE")

    def test_blocked_work_cannot_lose_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            with self.assertRaises(ValueError):
                mod.transition(path, work_id="wi-1", target="blocked", actor="agent", next_action="wait")
            blocked = mod.transition(
                path, work_id="wi-1", target="blocked", actor="agent",
                next_action="retry after credentials", blocker="credential unavailable",
            )
            self.assertEqual(blocked["status"], "blocked")

    def test_board_projection_survives_context_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            board = Path(temp) / "TASK_BOARD.md"
            board.write_text("# Existing Board\n\n## Other\n", encoding="utf-8")
            self.register(path)
            mod.project_board(path, board)
            first = board.read_text(encoding="utf-8")
            self.assertIn("[WI:wi-1] implement code", first)
            self.assertIn("Existing Board", first)
            mod.project_board(path, board)
            second = board.read_text(encoding="utf-8")
            self.assertEqual(second.count("<!-- WORK_COMPLETION_START -->"), 1)
            self.assertEqual(second.count("[WI:wi-1]"), 1)

    def test_work_item_can_pin_a_non_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            workspace = str(Path(temp) / "workspace")
            item = mod.register(
                path,
                work_id="wi-workspace",
                project_id="agentmanager",
                title="continue safely",
                owner="role://completion.controller",
                next_action="resume implementation",
                acceptance=["verified receipt"],
                workspace=workspace,
            )
            self.assertEqual(item["workspace"], workspace)

    def test_stale_owner_is_reclaimed_for_autonomous_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            item = mod.register(
                path,
                work_id="wi-stale",
                project_id="agentmanager",
                title="must resume",
                owner="role://chat-session",
                next_action="finish implementation",
                acceptance=["production receipt"],
                lease_seconds=60,
            )
            state = mod.load(path)
            state["items"]["wi-stale"]["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            mod.save(path, state)
            reclaimed = mod.reclaim_stale(path, lease_seconds=600)
            self.assertEqual(reclaimed, ["wi-stale"])
            resumed = mod.load(path)["items"]["wi-stale"]
            self.assertEqual(resumed["owner"], "role://completion.controller")
            self.assertEqual(resumed["owner_generation"], 2)
            self.assertIn("[WI:wi-stale]", mod.board_projection(path))

    def test_stale_lobster_owner_is_reclaimed_to_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            item = mod.register(
                path,
                work_id="wi-lobster-stale",
                project_id="agentmanager",
                title="must recover executor crash",
                owner="role://completion.controller",
                next_action="finish implementation",
                acceptance=["verified"],
                lease_seconds=60,
            )
            mod.transition(
                path,
                work_id="wi-lobster-stale",
                target="in_progress",
                actor="role://lobster",
                next_action=item["next_action"],
                lease_seconds=60,
            )
            mod.handoff(
                path,
                work_id="wi-lobster-stale",
                actor="role://completion.controller",
                new_owner="role://lobster",
                next_action=item["next_action"],
                lease_seconds=60,
            )
            state = mod.load(path)
            state["items"]["wi-lobster-stale"]["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            mod.save(path, state)

            reclaimed = mod.reclaim_stale(path, lease_seconds=600)
            self.assertEqual(reclaimed, ["wi-lobster-stale"])
            resumed = mod.load(path)["items"]["wi-lobster-stale"]
            self.assertEqual(resumed["owner"], "role://completion.controller")
            self.assertEqual(resumed["status"], "in_progress")
            self.assertTrue(
                any(
                    h.get("event") == "stale_reclaim"
                    and h.get("from_owner") == "role://lobster"
                    and h.get("to_owner") == "role://completion.controller"
                    for h in resumed["history"]
                )
            )

    def test_live_external_owner_is_not_projected_to_lobster(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            mod.register(
                path,
                work_id="wi-live",
                project_id="agentmanager",
                title="active elsewhere",
                owner="role://chat-session",
                next_action="continue current implementation",
                acceptance=["verified"],
                lease_seconds=3600,
            )
            self.assertNotIn("[WI:wi-live]", mod.board_projection(path))


    def test_machine_verification_blocker_is_deferred_with_backoff(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="blocked", actor="role://lobster",
                next_action="retry verification", blocker="BLOCKED: 連續 3 次驗證失敗",
            )
            point = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
            result = mod.defer_machine_blockers(path, at=point)
            self.assertEqual(result[0]["blocker_kind"], "VERIFICATION")
            self.assertEqual(result[0]["retry_count"], 1)
            self.assertEqual(result[0]["delay_seconds"], 300)
            item = mod.load(path)["items"]["wi-1"]
            self.assertEqual(item["status"], "waiting_external")
            self.assertEqual(item["owner"], "role://completion.controller")
            self.assertEqual(item["last_blocker_kind"], "VERIFICATION")
            self.assertEqual(item["machine_retry_count"], 1)
            self.assertEqual(
                item["wake_condition"]["not_before"],
                "2026-10-08T00:05:00+00:00",
            )

    def test_machine_blocker_backoff_increases_and_is_capped(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            state = mod.load(path)
            item = state["items"]["wi-1"]
            item["status"] = "blocked"
            item["blocker"] = "BLOCKED: provider rate limit"
            item["machine_retry_count"] = 4
            mod.save(path, state)
            result = mod.defer_machine_blockers(
                path, at=datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
            )
            self.assertEqual(result[0]["blocker_kind"], "PROVIDER_CAPACITY")
            self.assertEqual(result[0]["retry_count"], 5)
            self.assertEqual(result[0]["delay_seconds"], 3600)

    def test_human_and_unknown_blockers_stay_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="blocked", actor="role://lobster",
                next_action="wait for login", blocker="BLOCKED: human login required",
            )
            self.assertEqual(mod.defer_machine_blockers(path), [])
            self.assertEqual(mod.load(path)["items"]["wi-1"]["status"], "blocked")

        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="blocked", actor="role://lobster",
                next_action="inspect unknown", blocker="BLOCKED: opaque domain-specific blocker",
            )
            self.assertEqual(mod.defer_machine_blockers(path), [])
            self.assertEqual(mod.load(path)["items"]["wi-1"]["status"], "blocked")

    def test_deferred_machine_blocker_wakes_without_human_continue(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="blocked", actor="role://lobster",
                next_action="retry verification", blocker="BLOCKED: verification failed",
            )
            point = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
            mod.defer_machine_blockers(path, at=point)
            self.assertIsNone(mod.next_item(path))
            awakened = mod.wake_due(path, at=point + timedelta(minutes=6))
            self.assertEqual(awakened, ["wi-1"])
            item = mod.load(path)["items"]["wi-1"]
            self.assertEqual(item["status"], "accepted")
            self.assertEqual(item["owner"], "role://completion.controller")
            self.assertEqual(mod.next_item(path)["work_id"], "wi-1")

    def test_wait_external_is_durable_but_not_executable_until_due(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="in_progress",
                actor="role://completion.controller", next_action="wait for CI",
            )
            waiting = mod.wait_external(
                path,
                work_id="wi-1",
                actor="role://lobster",
                not_before="2099-01-01T00:00:00+00:00",
                next_action="inspect CI result",
                reason="github workflow still running",
            )
            self.assertEqual(waiting["status"], "waiting_external")
            self.assertEqual(waiting["owner"], "role://completion.controller")
            self.assertEqual(waiting["wake_condition"]["kind"], "time")
            self.assertIsNone(mod.next_item(path))

    def test_due_external_wait_is_woken_without_human_nudge(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(
                path, work_id="wi-1", target="in_progress",
                actor="role://completion.controller", next_action="wait for retry window",
            )
            mod.wait_external(
                path,
                work_id="wi-1",
                actor="role://lobster",
                not_before="2000-01-01T00:00:00+00:00",
                next_action="retry automatically",
            )
            awakened = mod.wake_due(path)
            self.assertEqual(awakened, ["wi-1"])
            item = mod.load(path)["items"]["wi-1"]
            self.assertEqual(item["status"], "accepted")
            self.assertIsNone(item["wake_condition"])
            self.assertEqual(mod.next_item(path)["work_id"], "wi-1")
            self.assertTrue(any(h.get("event") == "wake" for h in item["history"]))

    def test_wait_external_requires_typed_wake_condition(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            with self.assertRaises(ValueError):
                mod.wait_external(
                    path,
                    work_id="wi-1",
                    actor="agent",
                    not_before="not-a-time",
                    next_action="resume",
                )

    def test_verified_done_helper_walks_required_states(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            item = mod.verified_done(path, work_id="wi-1", actor="lobster+inspector", evidence="physical-output-pass")
            self.assertEqual(item["status"], "done")
            self.assertEqual(mod.audit(path), ([], []))



    def test_provider_quota_recovery_is_model_free_and_fenced(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            mod.register(
                path, work_id="quota-1", project_id="agentmanager",
                title="recover after provider exhaustion",
                owner="executor://oracle-gemini",
                next_action="run the remaining checks",
                acceptance=["receipt and tests"],
            )
            recovered = mod.recover_provider_failure(
                path, work_id="quota-1", actor="role://completion.controller",
                failed_owner="executor://oracle-gemini", expected_generation=1,
                failure_receipt="runtime://quota-001", failure_reason="provider quota exhausted",
                next_action="inspect local and remote Git SHA and any unacknowledged tool calls",
            )
            self.assertEqual(recovered["owner_generation"], 2)
            self.assertEqual(recovered["status"], "blocked")
            self.assertIsNone(mod.next_item(path))
            with self.assertRaisesRegex(ValueError, "stale_generation"):
                mod.assert_execution_fence(
                    path, work_id="quota-1", owner="executor://oracle-gemini", generation=1,
                )
            with self.assertRaisesRegex(ValueError, "stale_generation"):
                mod.recover_provider_failure(
                    path, work_id="quota-1", actor="role://completion.controller",
                    failed_owner="executor://oracle-gemini", expected_generation=1,
                    failure_receipt="runtime://quota-001", failure_reason="provider quota exhausted",
                    next_action="resume",
                )

    def test_provider_quota_recovery_rejects_untrusted_actor_and_wrong_error_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            mod.register(
                path, work_id="quota-2", project_id="agentmanager",
                title="preserve ownership", owner="executor://oracle-gemini",
                next_action="finish safely", acceptance=["receipt"],
            )
            for actor, reason in [
                ("executor://other-model", "provider quota exhausted"),
                ("role://completion.controller", "human login required"),
            ]:
                with self.assertRaises(ValueError):
                    mod.recover_provider_failure(
                        path, work_id="quota-2", actor=actor,
                        failed_owner="executor://oracle-gemini", expected_generation=1,
                        failure_receipt="runtime://quota-002", failure_reason=reason,
                        next_action="inspect",
                    )
            self.assertEqual(mod.load(path)["items"]["quota-2"]["owner_generation"], 1)


    def test_oracle_install_preflight_recognizes_durable_waiting_external(self):
        """Regression for Oracle installer failure on a valid timed wait.

        Execute the workflow's exact inline assertion against minimal state
        fixtures. This must reject malformed/unowned waits, not just allow all
        waiting_external records unconditionally.
        """
        import contextlib
        import io
        import json
        import re
        import sys
        import textwrap
        from unittest.mock import patch

        workflow = (ROOT / ".github/workflows/oracle-install-completion-controller.yml").read_text()
        marker = 'register-intake --input "$INTAKE"'
        start = workflow.index(marker) + len(marker)
        block = re.search(
            r'          python3 - "\$STATE" <<\'PY\'\n(.*?)\n          PY',
            workflow[start:], re.S,
        )
        self.assertIsNotNone(block)
        script = textwrap.dedent(block.group(1))
        work_id = "market-master-1200-mvp"

        def evaluate(status, owner, wake=None):
            with tempfile.TemporaryDirectory() as temp:
                state = Path(temp) / "state.json"
                state.write_text(json.dumps({"items": {work_id: {
                    "project_id": "market-master-evolution",
                    "status": status, "owner": owner,
                    "wake_condition": wake,
                }}}))
                with patch.object(sys, "argv", ["preflight", str(state)]), contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(script, "<oracle-completion-preflight>", "exec"), {"__name__": "__main__"})

        valid_wake = {"kind": "time", "not_before": "2099-01-01T00:00:00Z"}
        evaluate("waiting_external", "role://completion.controller", valid_wake)
        evaluate("accepted", "role://completion.controller")
        evaluate("in_progress", "role://lobster")
        with self.assertRaises(AssertionError):
            evaluate("waiting_external", "role://lobster", valid_wake)
        with self.assertRaises(AssertionError):
            evaluate("waiting_external", "role://completion.controller", None)
        with self.assertRaises(AssertionError):
            evaluate("unknown_state", "role://completion.controller")

if __name__ == "__main__":
    unittest.main()
