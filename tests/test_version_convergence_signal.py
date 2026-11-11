import unittest
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

if __name__=="__main__": unittest.main()
