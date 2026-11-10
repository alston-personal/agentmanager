import unittest
from agent_core.hermes_handoff import handoff_proposal

C = {"repo":"example/project", "source_url":"https://github.com/example/project",
     "classification":"REUSABLE_COMPONENT"}

def route(candidate=C, **kwargs):
    args=dict(candidate=candidate,existing_owner_ref=None,gap_confirmed=True,
              license_review_passed=True,security_review_passed=True,
              implementation_spec_ready=False)
    args.update(kwargs)
    return handoff_proposal(**args)

class HermesHandoffTests(unittest.TestCase):
    def test_existing_owner_reused(self):
        p=route(existing_owner_ref="github:alston-personal/agentmanager#470")
        self.assertEqual(p["suggested_owner"],"canonical_issue_owner")
        self.assertFalse(p["work_item_created"])
    def test_weaver_receives_unscoped_gap(self):
        self.assertEqual(route()["suggested_owner"],"sector.weaver")
    def test_paw_only_if_spec_ready(self):
        p=route(implementation_spec_ready=True)
        self.assertEqual(p["suggested_owner"],"sector.paw")
        self.assertFalse(p["execution_authorized"])
    def test_claw_receives_risky_candidate(self):
        self.assertEqual(route(license_review_passed=False)["suggested_owner"],"sector.claw")
    def test_reject_not_routed_to_paw(self):
        c={**C,"classification":"REJECTED"}
        self.assertEqual(route(candidate=c,implementation_spec_ready=True)["suggested_owner"],"research.hermes")
    def test_existing_equivalent_not_assigned(self):
        self.assertEqual(route(gap_confirmed=False)["route_reason"],"existing_equivalent")
    def test_bad_source_denied(self):
        with self.assertRaises(ValueError):
            route(candidate={**C,"source_url":"https://malicious.example/"})
    def test_invalid_owner_denied(self):
        with self.assertRaises(ValueError):
            route(existing_owner_ref="anything")

if __name__=="__main__":
    unittest.main()
