import unittest
from scripts.version_convergence_signal import validate_adapter_hint, plan_adapter_reconciliation
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

if __name__=="__main__": unittest.main()
