import unittest
from agent_core.bounty_pdca import BountyCycle, advance_bounty_cycle, plan_next_work, cycle_receipt

class BountyPdcaTests(unittest.TestCase):
    def test_one_wake_per_transition(self):
        a = advance_bounty_cycle(BountyCycle(), {"type":"CANDIDATE_SELECTED","issue":"Parabola#18"})
        self.assertEqual((a.stage,a.revision),("DO",1))
        self.assertEqual(advance_bounty_cycle(a, {"type":"CANDIDATE_SELECTED","issue":"Parabola#18"}),a)

    def test_waiting_external_does_not_block_next_candidate(self):
        a = BountyCycle("Parabola#18","WAITING_EXTERNAL",3)
        self.assertEqual(plan_next_work([a],["Parabola#18","Parabola#16"]),"Parabola#16")

    def test_auth_denied_requires_explicit_grant(self):
        a = advance_bounty_cycle(BountyCycle("Parabola#18","DO"),{"type":"AUTH_DENIED"})
        self.assertEqual(a.stage,"AUTH_REQUIRED")
        self.assertEqual(advance_bounty_cycle(a,{"type":"PR_SUBMITTED"}),a)

    def test_payment_must_be_verified(self):
        a = BountyCycle("Parabola#18","WAITING_EXTERNAL")
        self.assertEqual(advance_bounty_cycle(a,{"type":"PR_ACCEPTED"}).stage,"CHECK")
        self.assertFalse(cycle_receipt(a)["bountyPaid"])
        b = advance_bounty_cycle(a,{"type":"VERIFIED_SETTLEMENT"})
        self.assertTrue(cycle_receipt(b)["bountyPaid"])

    def test_lesson_returns_plan(self):
        a = advance_bounty_cycle(BountyCycle("Parabola#18","ACT"),{"type":"LESSON_RECORDED"})
        self.assertEqual((a.issue,a.stage),(None,"PLAN"))

if __name__ == "__main__":
    unittest.main()
