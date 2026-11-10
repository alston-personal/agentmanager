import unittest
from agent_core.employee_autonomy_gate import AutonomyEvidence,evaluate_minimum_autonomy,from_verified_receipts

class MinimumAutonomyGateTests(unittest.TestCase):
    def test_declaration_without_wake_is_not_live(self):
        flags=dict.fromkeys(AutonomyEvidence.__dataclass_fields__,True)
        flags["supervisor_wake_receipt"]=False
        result=from_verified_receipts(flags)
        self.assertEqual(result["status"],"NOT_VERIFIED")
    def test_first_scan_only_is_not_live(self):
        flags=dict.fromkeys(AutonomyEvidence.__dataclass_fields__,True)
        flags["second_cycle_receipt"]=False
        self.assertIn("second_cycle_receipt",from_verified_receipts(flags)["missing"])
    def test_strings_cannot_claim_operating_proof(self):
        flags=dict.fromkeys(AutonomyEvidence.__dataclass_fields__,"true")
        self.assertFalse(from_verified_receipts(flags)["may_claim_persistent_operation"])
    def test_all_proven_live(self):
        flags=dict.fromkeys(AutonomyEvidence.__dataclass_fields__,True)
        self.assertEqual(from_verified_receipts(flags)["status"],"LIVE_VERIFIED")
if __name__=="__main__":
    unittest.main()
