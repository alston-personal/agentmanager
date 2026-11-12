import unittest
from scripts.version_convergence_signal import validate_adapter_hint, plan_adapter_reconciliation, gate_adapter_install, PREFLIGHT_CHECKS, initial_channel_state, reconcile_channel_update
from scripts.version_convergence_signal import make_event, validate_ack, affected_domains
A="a"*40
B="b"*40

class VersionSignalTests(unittest.TestCase):
    def event(self):
        return make_event(repository="alston-personal/agentmanager",main_sha=A,
            previous_sha=B,changed_paths=["docs/CURRENT_STATE.md","agent_core/controller_api.py"],
            published_at="2026-11-11T15:00:00Z",pr_number=2256)

    def ack(self,event,state="NOTIFIED"):
        return {"schema":"agentos.version-convergence-ack/v1","event_id":event["event_id"],
                "target_main_sha":event["target_main_sha"],"executor_id":"oracle-gemini",
                "task_id":"issue-1682","state":state,"observed_base_sha":B,
                "deployed_source_sha":None,"dirty_worktree_preserved":True,
                "write_authorized":False,"acknowledged_at":"2026-11-11T15:01:00Z"}

    def test_event_determinism(self):
        e=self.event()
        self.assertEqual(e["affected_domains"],["core","governance"])
        self.assertFalse(e["execution_authorized"])
        other=make_event(repository=e["repository"],main_sha=A,previous_sha=B,
            changed_paths=list(reversed(e["changed_paths"])),
            published_at=e["published_at"],pr_number=2256)
        self.assertEqual(other,e)

    def test_notification_is_not_convergence_or_deployment(self):
        event=self.event()
        ack=self.ack(event)
        self.assertEqual(validate_ack(event,ack)["state"],"NOTIFIED")
        ack["state"]="SOURCE_CONVERGED"
        with self.assertRaises(ValueError): validate_ack(event,ack)
        ack["observed_base_sha"]=A
        self.assertEqual(validate_ack(event,ack)["state"],"SOURCE_CONVERGED")
        ack["state"]="RUNTIME_DEPLOYED"
        with self.assertRaises(ValueError): validate_ack(event,ack)
        ack["deployed_source_sha"]=A
        self.assertEqual(validate_ack(event,ack)["state"],"RUNTIME_DEPLOYED")

    def test_security_guards(self):
        event=self.event()
        ack=self.ack(event)
        for key,value in [("event_id","forged"),("write_authorized",True),
                          ("dirty_worktree_preserved",False),("executor_id","../../evil")]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_ack(event,{**ack,key:value})
        with self.assertRaises(ValueError): affected_domains(["../../secrets"])
        with self.assertRaises(ValueError):
            make_event(repository="alston-personal/agentmanager",main_sha=A,previous_sha=A,
                changed_paths=["docs/a.md"],published_at="2026-11-11T15:00:00Z")
        with self.assertRaises(ValueError):
            make_event(repository="alston-personal/agentmanager",main_sha=A,previous_sha=B,
                changed_paths=["docs/a.md"],published_at="2026-11-11")


class AdapterBootstrapTests(unittest.TestCase):
    def hint(self):
        return {
            "schema": "agentos.adapter-invalidation-hint/v1",
            "notice_epoch": 14,
            "adapter_id": "ir.handler",
            "adapter_url": "https://one.example.test/adapters/ir.handler/v1",
            "adapter_version": "1.4.0",
            "adapter_sha256": "a" * 64,
        }

    def plan(self, hint=None, **installed):
        hint = hint or self.hint()
        manifest = {
            "adapter_id": hint["adapter_id"],
            "adapter_url": hint["adapter_url"],
            "adapter_version": hint["adapter_version"],
            "adapter_sha256": hint["adapter_sha256"],
            "approved": True,
        }
        return plan_adapter_reconciliation(
            hint=hint, trusted_one_origin="https://one.example.test",
            authoritative_manifest=manifest, **installed)

    def test_absent_or_old_adapter_requests_governed_update(self):
        self.assertEqual(self.plan()["action"], "REQUEST_GOVERNED_ADAPTER_UPDATE")
        self.assertEqual(self.plan(installed_version="1.3.9", installed_sha256="b"*64)["action"],
                         "REQUEST_GOVERNED_ADAPTER_UPDATE")
        self.assertEqual(self.plan(installed_version="1.4.0", installed_sha256="b"*64)["action"],
                         "REQUEST_GOVERNED_ADAPTER_UPDATE")
        self.assertFalse(self.plan()["installation_authorized"])

    def test_exact_installed_adapter_can_handle_after_separate_authority(self):
        result = self.plan(installed_version="1.4.0", installed_sha256="a"*64)
        self.assertEqual(result["action"], "HANDLE_EVENT")
        self.assertFalse(result["handler_execution_authorized"])
        self.assertEqual(self.plan(installed_version="1.5.0", installed_sha256="b"*64)["action"],
                         "KEEP_NEWER_LOCAL_AND_VERIFY_COMPATIBILITY")

    def test_locator_cannot_grant_authority_or_redirect_to_attacker(self):
        hint = self.hint()
        bad = [
            {**hint, "adapter_url": "https://evil.test/payload"},
            {**hint, "adapter_url": "http://one.example.test/adapters/evil"},
            {**hint, "adapter_url": "https://one.example.test@evil.test/file"},
            {**hint, "adapter_url": "https://one.example.test/a/../secrets"},
            {**hint, "adapter_url": "https://one.example.test/a?token=abc"},
            {**hint, "adapter_sha256": "invalid"},
            {**hint, "notice_epoch": 0},
            {**hint, "install_now": True},
        ]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    validate_adapter_hint(item, trusted_one_origin="https://one.example.test")
        with self.assertRaises(ValueError):
            validate_adapter_hint(hint, trusted_one_origin="http://one.example.test")

    def test_hint_never_supersedes_one_authoritative_manifest(self):
        hint = self.hint()
        m = {key:hint[key] for key in (
            "adapter_id","adapter_url","adapter_version","adapter_sha256")}
        for item in ({**m,"approved":False},
                     {**m,"approved":True,"adapter_version":"1.5.0"},
                     {**m,"approved":True,"adapter_sha256":"b"*64}):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    plan_adapter_reconciliation(
                        hint=hint, trusted_one_origin="https://one.example.test",
                        authoritative_manifest=item)


class SafeUpdateRecoveryTests(unittest.TestCase):
    def fixtures(self):
        plan = {
            "schema": "agentos.adapter-reconciliation-plan/v1",
            "adapter_id": "ir.handler", "target_adapter_version": "1.4.0",
            "notice_epoch": 14, "action": "REQUEST_GOVERNED_ADAPTER_UPDATE",
            "installation_authorized": False,
        }
        attestation = {
            "schema": "agentos.adapter-preflight-attestation/v1",
            "adapter_id": "ir.handler", "adapter_version": "1.4.0",
            "notice_epoch": 14, "trusted_source_attested": True,
            "checks": {check: True for check in PREFLIGHT_CHECKS},
        }
        recovery = {
            "independent_process": True, "protected_from_adapter_update": True,
            "one_handshake_verified": True, "last_known_good_verified": True,
            "rollback_ready": True,
        }
        return plan, attestation, recovery

    def test_all_preflight_and_rescue_proofs_allow_only_staged_request(self):
        p, a, r = self.fixtures()
        result = gate_adapter_install(plan=p, attestation=a, recovery=r)
        self.assertEqual(result["action"], "REQUEST_AUTHORIZED_STAGED_INSTALL")
        self.assertFalse(result["installation_authorized"])
        self.assertFalse(result["activation_authorized"])

    def test_each_preflight_failure_blocks(self):
        p, a, r = self.fixtures()
        for check in PREFLIGHT_CHECKS:
            bad = {**a, "checks": {**a["checks"], check: False}}
            with self.subTest(check=check), self.assertRaises(ValueError):
                gate_adapter_install(plan=p, attestation=bad, recovery=r)
        with self.assertRaises(ValueError):
            gate_adapter_install(plan=p, attestation={**a, "notice_epoch": 15}, recovery=r)
        with self.assertRaises(ValueError):
            gate_adapter_install(plan=p, attestation={**a, "trusted_source_attested": False}, recovery=r)

    def test_each_recovery_failure_blocks_even_if_adapter_tests_pass(self):
        p, a, r = self.fixtures()
        for check in r:
            with self.subTest(check=check), self.assertRaises(ValueError):
                gate_adapter_install(plan=p, attestation=a, recovery={**r, check: False})
        with self.assertRaises(ValueError):
            gate_adapter_install(plan={**p, "installation_authorized": True},
                                 attestation=a, recovery=r)



class DualChannelInterlockTests(unittest.TestCase):
    def step(self, state, stage, lane="normal", op="op-1", observed=None):
        return reconcile_channel_update(
            state=state, stage=stage, lane=lane, operation_id=op,
            observed=observed, expected_generation=state["generation"])

    def begin_proof(self, lane):
        return ({"recovery_one_handshake": True, "recovery_signed_manifest": True,
                 "recovery_rollback_ready": True} if lane == "normal" else
                {"normal_one_handshake": True, "normal_recovery_download": True,
                 "protected_recovery_slot_ready": True})

    def test_normal_update_needs_independent_recovery(self):
        start = initial_channel_state()
        evidence = self.begin_proof("normal")
        for key in evidence:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.step(start, "BEGIN", observed={**evidence, key: False})
        started = self.step(start, "BEGIN", observed=evidence)
        self.assertEqual(started["active_lane"], "normal")
        with self.assertRaises(ValueError):
            self.step(started, "BEGIN", lane="recovery",
                      observed=self.begin_proof("recovery"))

    def test_recovery_update_prioritized_but_requires_normal_fallback(self):
        start = initial_channel_state()
        evidence = self.begin_proof("recovery")
        for key in evidence:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.step(start, "BEGIN", lane="recovery",
                          observed={**evidence, key: False})
        begun = self.step(start, "BEGIN", lane="recovery", observed=evidence)
        with self.assertRaises(ValueError):
            self.step(begun, "BEGIN", lane="normal", observed=self.begin_proof("normal"))
        with self.assertRaises(ValueError):
            self.step(begun, "VERIFY", lane="recovery", observed={})

    def test_activation_requires_separate_authority_and_fallback(self):
        state = self.step(initial_channel_state(), "BEGIN",
                          observed=self.begin_proof("normal"))
        with self.assertRaises(ValueError):
            self.step(state, "ACTIVATE", observed={
                "preflight_passed": True, "fallback_still_healthy": True})
        state = self.step(state, "ACTIVATE", observed={
            "preflight_passed": True, "fallback_still_healthy": True,
            "activation_separately_authorized": True})
        with self.assertRaises(ValueError):
            self.step(state, "VERIFY", observed={
                "updated_lane_one_handshake": True,
                "updated_lane_signed_manifest": True,
                "fallback_still_healthy": True})
        state = self.step(state, "VERIFY", observed={
            "updated_lane_one_handshake": True,
            "updated_lane_signed_manifest": True,
            "fallback_still_healthy": True,
            "one_receipt_attested": True})
        self.assertEqual(state["phase"], "IDLE")
        self.assertEqual(state["last_verified_lane"], "normal")

    def test_rescue_update_can_verify_then_allow_normal(self):
        state = self.step(initial_channel_state(), "BEGIN", lane="recovery",
                          observed=self.begin_proof("recovery"))
        state = self.step(state, "ACTIVATE", lane="recovery", observed={
            "preflight_passed": True, "fallback_still_healthy": True,
            "activation_separately_authorized": True})
        state = self.step(state, "VERIFY", lane="recovery", observed={
            "updated_lane_one_handshake": True,
            "updated_lane_signed_manifest": True,
            "fallback_still_healthy": True,
            "one_receipt_attested": True})
        self.assertEqual(state["last_verified_lane"], "recovery")
        started_normal = self.step(state, "BEGIN", observed=self.begin_proof("normal"))
        self.assertEqual(started_normal["active_lane"], "normal")

    def test_failure_blocks_second_update_until_verified_rollback(self):
        state = self.step(initial_channel_state(), "BEGIN",
                          observed=self.begin_proof("normal"))
        state = self.step(state, "FAIL")
        self.assertEqual(state["phase"], "ROLLBACK_REQUIRED")
        with self.assertRaises(ValueError):
            self.step(state, "BEGIN", lane="recovery",
                      observed=self.begin_proof("recovery"))
        with self.assertRaises(ValueError):
            self.step(state, "ROLLBACK_OK", observed={
                "fallback_still_healthy": True, "restored_lane_one_handshake": True})
        state = self.step(state, "ROLLBACK_OK", observed={
            "fallback_still_healthy": True, "restored_lane_one_handshake": True,
            "one_rollback_receipt_attested": True})
        self.assertEqual(state["phase"], "IDLE")

    def test_stale_generation_and_unrecoverable_failure_fail_closed(self):
        state = self.step(initial_channel_state(), "BEGIN",
                          observed=self.begin_proof("normal"))
        with self.assertRaises(ValueError):
            reconcile_channel_update(
                state=state, stage="ACTIVATE", lane="normal", operation_id="op-1",
                expected_generation=0,
                observed={"preflight_passed": True, "fallback_still_healthy": True,
                          "activation_separately_authorized": True})
        with self.assertRaises(ValueError):
            self.step(state, "FAIL", op="different-operation")
        state = self.step(state, "FAIL")
        state = self.step(state, "ROLLBACK_FAILED")
        self.assertEqual(state["phase"], "HUMAN_REQUIRED")
        with self.assertRaises(ValueError):
            self.step(state, "BEGIN", observed=self.begin_proof("normal"))

if __name__=="__main__": unittest.main()
