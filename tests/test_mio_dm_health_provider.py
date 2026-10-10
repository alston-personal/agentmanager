from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job, ExecutorJobContractError
from agentos_node import mio_dm_health_provider as health
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry, run_registered_executor_job
from agentos_node.executor_job_action_relay import ActionRelayExecutorJobDispatcher
from agentos_node.action_relay import ActionRelayWorker

ROOT = Path(__file__).resolve().parents[1]
REQUEST = canonical_executor_job_request(health.JOB_TYPE)


def markers(state="AUTHENTICATED", account="EXPECTED"):
    return "\n".join((
        "threads_web_dm_login_probe=PASS", "threads_web_dm_login_mode=oracle_gui_worker",
        "threads_web_dm_login_session_state=" + state,
        "threads_web_dm_login_account_state=" + account,
    ))


class MioDMHealthTests(unittest.TestCase):
    def invoke(self, stdout=None, returncode=0, process=None):
        proc = process or Mock(returncode=returncode, pid=12345)
        if process is None:
            proc.communicate.return_value = (markers() if stdout is None else stdout, "private stderr secret")
        with patch.object(health.Path, "home", return_value=health.EXPECTED_HOME), \
             patch.dict(health.os.environ, {"USER": "ubuntu"}), \
             patch.object(health, "_unit_state", return_value="active"), \
             patch.object(health, "_timer_enabled", return_value=True), \
             patch.object(health, "_cycle_health", return_value={"dm_oursong_cycle_status":"UNKNOWN", "dm_oursong_cycle_fresh":False}), \
             patch.object(health.subprocess, "Popen", return_value=proc) as launch:
            return health.run_mio_dm_health(REQUEST, runtime_root=ROOT), launch, proc

    def test_fixed_read_only_contract_and_no_override(self):
        self.assertTrue(validate_executor_job(REQUEST).read_only)
        self.assertEqual(REQUEST["executor_class"], "oracle-gui-worker")
        for field, value in (("workload_ref", "persona://oursong/threads-dm"),
                             ("command", "anything"), ("env", {}), ("path", "/tmp")):
            with self.subTest(field=field), self.assertRaises(ExecutorJobContractError):
                validate_executor_job({**REQUEST, field:value})

    def test_authenticated_mio_is_session_pass_without_claiming_cycle_success(self):
        result, launch, _ = self.invoke()
        self.assertTrue(result["successful"])
        self.assertEqual(result["dm_account_state"], "EXPECTED")
        self.assertFalse(result["dm_oursong_cycle_fresh"])
        argv = launch.call_args.args[0]
        self.assertEqual(argv, ["/bin/bash", str(ROOT / "scripts/probe_threads_web_dm_login_user.sh")])
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertNotIn("private stderr", json.dumps(result))

    def test_logout_and_blocked_are_not_healthy(self):
        for state in ("LOGIN_REQUIRED", "BLOCKED", "UNKNOWN"):
            with self.subTest(state=state):
                result, _, _ = self.invoke(markers(state, "UNKNOWN"))
                self.assertEqual(result["dm_session_state"], state)
                self.assertFalse(result["successful"])

    def test_wrong_or_missing_identity_fails_closed(self):
        for account in ("MISMATCH", "AMBIGUOUS", "UNKNOWN"):
            with self.subTest(account=account):
                result, _, _ = self.invoke(markers(account=account))
                self.assertFalse(result["successful"])
                self.assertEqual(result["classification"], "MIO_DM_ACCOUNT_" + account)

    def test_old_probe_without_account_marker_is_not_accepted(self):
        result, _, _ = self.invoke(markers().replace("threads_web_dm_login_account_state=EXPECTED", ""))
        self.assertFalse(result["successful"])
        self.assertEqual(result["classification"], "MIO_DM_ACCOUNT_UNKNOWN")

    def test_duplicate_or_unrecognized_markers_fail_closed(self):
        for suffix in ("\nthreads_web_dm_login_session_state=LOGIN_REQUIRED",
                       "\nthreads_web_dm_login_probe=PASS"):
            result, _, _ = self.invoke(markers() + suffix)
            self.assertEqual(result["dm_session_state"], "UNKNOWN")
        result, _, _ = self.invoke(markers("secret arbitrary text", "EXPECTED"))
        self.assertFalse(result["successful"])
        self.assertNotIn("secret arbitrary text", json.dumps(result))

    def test_failed_probe_cannot_claim_pass_from_stdout(self):
        result, _, _ = self.invoke(returncode=1)
        self.assertEqual(result["classification"], "MIO_DM_SESSION_PROBE_FAILED")

    def test_wrong_executor_user_does_not_launch_probe(self):
        with patch.object(health.Path, "home", return_value=Path("/root")), \
             patch.object(health.subprocess, "Popen") as launch:
            result = health.run_mio_dm_health(REQUEST, runtime_root=ROOT)
            self.assertFalse(result["authorized"])
            launch.assert_not_called()

    def test_timeout_kills_only_its_own_process_group(self):
        proc = Mock(returncode=-9, pid=12345)
        proc.communicate.side_effect = [subprocess.TimeoutExpired("probe",90), ("secret", "secret")]
        with patch.object(health.os, "killpg") as kill:
            result, _, _ = self.invoke(process=proc)
            kill.assert_called_once_with(12345, health.signal.SIGKILL)
        self.assertEqual(result["classification"], "MIO_DM_SESSION_PROBE_TIMEOUT")
        self.assertNotIn("secret", json.dumps(result))

    def test_cycle_receipt_freshness_and_private_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "20261010T142000Z.json"
            raw = {"schema":"agentos.mio-dm-cycle-receipt/v1", "created_at":datetime.now(timezone.utc).isoformat(),
                   "status":"ALIVE_IDLE", "peer":"private peer", "text":"private message", "message_id":"private id"}
            path.write_text(json.dumps(raw))
            result = health._cycle_health(root)
            self.assertTrue(result["dm_oursong_cycle_fresh"])
            self.assertEqual(result["dm_oursong_cycle_status"], "ALIVE_IDLE")
            self.assertNotIn("private", json.dumps(result))
            raw["created_at"] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
            path.write_text(json.dumps(raw))
            self.assertFalse(health._cycle_health(root)["dm_oursong_cycle_fresh"])

    def test_bad_future_or_naive_cycle_receipt_does_not_establish_freshness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "20261010T142000Z.json"
            for stamp in ("invalid", datetime.now().isoformat(), (datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()):
                path.write_text(json.dumps({"schema":"agentos.mio-dm-cycle-receipt/v1", "created_at":stamp, "status":"PASS_REPLY"}))
                self.assertFalse(health._cycle_health(root)["dm_oursong_cycle_fresh"])

    def test_latest_malformed_receipt_does_not_fall_back_to_old_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"20261009.json").write_text(json.dumps({"schema":"agentos.mio-dm-cycle-receipt/v1", "created_at":datetime.now(timezone.utc).isoformat(), "status":"PASS_REPLY"}))
            (root/"20261010.json").write_text("broken")
            self.assertEqual(health._cycle_health(root)["dm_oursong_cycle_status"], "UNKNOWN")

    def test_symlink_or_oversized_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"outside").write_text("private")
            (root/"20261010.json").symlink_to(root/"outside")
            self.assertFalse(health._cycle_health(root)["dm_oursong_cycle_fresh"])
            (root/"20261010.json").unlink()
            (root/"20261010.json").write_text("x"*65537)
            self.assertFalse(health._cycle_health(root)["dm_oursong_cycle_fresh"])

    def test_registry_is_idempotent_but_rejects_conflicting_provider(self):
        registry = ExecutorJobProviderRegistry()
        self.assertTrue(health.register_mio_dm_health_provider(registry=registry))
        self.assertTrue(health.register_mio_dm_health_provider(registry=registry))
        other = ExecutorJobProviderRegistry()
        other.register(job_type=health.JOB_TYPE, provider_id="wrong", executor_class=health.EXECUTOR_CLASS, handler=lambda x:{})
        with self.assertRaises(RuntimeError):
            health.register_mio_dm_health_provider(registry=other)

    def test_public_mailbox_independently_rejects_private_or_wrong_types(self):
        from agent_core.control_inbox_bridge import _project_receipt
        base = {"schema":"agentos.executor-job-receipt/v1", "job_type":health.JOB_TYPE,
                "dm_session_state":"AUTHENTICATED", "dm_account_state":"EXPECTED",
                "dm_oursong_cycle_status":"ALIVE_IDLE", "dm_oursong_cycle_fresh":False,
                "dm_oursong_cycle_age_seconds":123, "dm_checked_at":"2026-10-10T14:00:00Z",
                "text":"private message", "peer":"private peer", "stdout":"private output"}
        projected = _project_receipt(base, "agentos.executor.job")
        self.assertEqual(projected["dm_session_state"], "AUTHENTICATED")
        self.assertFalse(projected["dm_oursong_cycle_fresh"])
        self.assertNotIn("private", json.dumps(projected))
        bad = _project_receipt({**base, "dm_session_state":"private message",
                               "dm_oursong_cycle_age_seconds":True,
                               "dm_checked_at":"private text", "dm_oursong_cycle_fresh":"true"}, "agentos.executor.job")
        for field in ("dm_session_state", "dm_oursong_cycle_age_seconds", "dm_checked_at", "dm_oursong_cycle_fresh"):
            self.assertNotIn(field, bad)
        self.assertNotIn("dm_session_state", _project_receipt({**base, "job_type":"codex.cli.health"}, "agentos.executor.job"))

    def invoke_resume(self, stdout, returncode=0, verified=None):
        proc = Mock(returncode=returncode, pid=54321)
        proc.communicate.return_value = (stdout, "private error")
        req = canonical_executor_job_request(health.RESUME_JOB_TYPE)
        with patch.object(health.Path, "home", return_value=health.EXPECTED_HOME), \
             patch.dict(health.os.environ, {"USER":"ubuntu"}), \
             patch.object(health.os, "access", return_value=True), \
             patch.object(health.subprocess, "Popen", return_value=proc) as launch, \
             patch.object(health, "run_mio_dm_health", return_value=verified or {"successful":False}) as verify:
            return health.run_mio_dm_resume(req, runtime_root=ROOT), launch, verify

    def test_resume_contract_is_separate_mutating_bounded_authority(self):
        req = canonical_executor_job_request(health.RESUME_JOB_TYPE)
        self.assertFalse(validate_executor_job(req).read_only)
        self.assertEqual(req["authority"], "bounded-persona-session-resume")
        with self.assertRaises(ExecutorJobContractError):
            validate_executor_job({**req, "authority":"bounded-read-only"})
        with self.assertRaises(ExecutorJobContractError):
            validate_executor_job({**req, "account":"oursong_alstonhuang"})

    def test_resume_only_reports_recovered_after_fresh_mio_health(self):
        result, launch, verify = self.invoke_resume("threads_persona_login_resume=PASS", verified={
            "successful":True, "dm_session_state":"AUTHENTICATED", "dm_account_state":"EXPECTED"})
        self.assertEqual(result["dm_resume_state"], "RECOVERED")
        self.assertTrue(result["successful"])
        verify.assert_called_once()
        env = launch.call_args.kwargs["env"]
        self.assertEqual(env["AGENTOS_DM_PERSONA"], "mio")
        self.assertTrue(env["PATH"].startswith("/home/ubuntu/.local/share/agentos/gui-worker/venv/bin:"))
        self.assertEqual(launch.call_args.args[0], ["/bin/bash", str(ROOT/"scripts/resume_threads_persona_login_user.sh")])

    def test_resume_pass_navigation_with_failed_identity_is_not_recovery(self):
        result, _, verify = self.invoke_resume("threads_persona_login_resume=PASS")
        self.assertEqual(result["classification"], "MIO_DM_RESUME_VERIFY_FAILED")
        self.assertFalse(result["successful"])
        verify.assert_called_once()

    def test_resume_human_required_is_explicit_and_no_further_action(self):
        result, _, verify = self.invoke_resume("threads_persona_login_resume_reason=ACCOUNT_HINT_MISSING\nthreads_persona_login_resume=HUMAN_REQUIRED")
        self.assertEqual(result["dm_resume_state"], "HUMAN_REQUIRED")
        self.assertEqual(result["dm_resume_reason"], "ACCOUNT_HINT_MISSING")
        self.assertFalse(result["successful"])
        verify.assert_not_called()
        self.assertNotIn("private", json.dumps(result))

    def test_resume_unknown_or_duplicate_markers_do_not_pass(self):
        for raw in ("threads_persona_login_resume=PASS\nthreads_persona_login_resume=HUMAN_REQUIRED", "private error"):
            result, _, verify = self.invoke_resume(raw)
            self.assertEqual(result["dm_resume_state"], "FAILED")
            verify.assert_not_called()

    def test_resume_nonzero_with_pass_marker_does_not_pass(self):
        result, _, verify = self.invoke_resume("threads_persona_login_resume=PASS", returncode=8)
        self.assertFalse(result["successful"])
        verify.assert_not_called()

    def test_existing_health_registration_can_add_resume_without_duplicate(self):
        registry = ExecutorJobProviderRegistry()
        registry.register(job_type=health.JOB_TYPE, provider_id=health.PROVIDER_ID, executor_class=health.EXECUTOR_CLASS, handler=health.run_mio_dm_health)
        health.register_mio_dm_health_provider(registry=registry)
        self.assertEqual(registry.get(health.RESUME_JOB_TYPE).provider_id, health.RESUME_PROVIDER_ID)

    def test_full_relay_submit_execute_restart_inspect_retains_health_only(self):
        from agentos_node import action_relay
        from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS
        with tempfile.TemporaryDirectory() as temp, patch.object(action_relay, "_share"), \
             patch.dict(DEFAULT_PROVIDERS._bindings, clear=True):
            DEFAULT_PROVIDERS.register(job_type=health.JOB_TYPE, provider_id=health.PROVIDER_ID,
                executor_class=health.EXECUTOR_CLASS, handler=lambda request:{
                    "verdict":"PASS", "classification":"MIO_DM_SESSION_AUTHENTICATED",
                    "dm_session_state":"AUTHENTICATED", "dm_account_state":"EXPECTED",
                    "dm_oursong_cycle_fresh":False, "credential_exposed":False,
                    "stdout":"private message body", "text":"private message", "token":"private token"})
            dispatcher = ActionRelayExecutorJobDispatcher(temp)
            submitted = dispatcher.submit(node_id="oracle-core-node", request=REQUEST)
            raw = ActionRelayWorker(temp).process_one()
            result = ActionRelayExecutorJobDispatcher(temp).inspect(submitted["job_id"])
            self.assertEqual(result["dm_account_state"], "EXPECTED")
            self.assertFalse(result["dm_oursong_cycle_fresh"])
            self.assertNotIn("private", json.dumps(raw))
            self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
