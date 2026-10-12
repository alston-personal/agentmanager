import copy
import unittest
from scripts.persona_ir_revision_gate import decide_persona_revision


class PersonaRevisionGateTests(unittest.TestCase):
    def setUp(self):
        self.old={"character_id":"mio", "revision":84,"ir_id":"mio-r84",
                  "current_self":{"voice":["calm"]},"promoted_growth":[{"growth_ref":"g1","status":"adopted"}]}
        self.new=copy.deepcopy(self.old)
        self.new.update(revision=85,parent_ir_id="mio-r84",ir_id="mio-r85")
        self.good={"growth_ref":"g2","validation":"PASS","governance":"APPROVED",
                   "source_event_ids":["receipt1"]}
    def promote(self):
        self.new["promoted_growth"].append({"growth_ref":"g2","status":"adopted"})
        self.new["current_self"]["voice"].append("curious")

    def test_experience_only_never_advances_ir(self):
        for count in (1,10,100):
            candidate=copy.deepcopy(self.new)
            candidate["journey"]={"total_events_seeded":count}
            self.assertEqual(decide_persona_revision(self.old,candidate)["status"],"NO_REVISION")

    def test_verified_promotion_allows_single_revision(self):
        self.promote()
        self.assertTrue(decide_persona_revision(self.old,self.new,self.good)["revision_allowed"])

    def test_mismatched_character_is_blocked(self):
        self.new["character_id"]="oursong"
        self.assertFalse(decide_persona_revision(self.old,self.new)["revision_allowed"])

    def test_missing_evidence_is_blocked(self):
        self.promote()
        self.assertEqual(decide_persona_revision(self.old,self.new)["reason"],"EVIDENCE_MISSING")

    def test_unreviewed_promotion_is_blocked(self):
        self.promote()
        self.assertEqual(decide_persona_revision(self.old,self.new,{**self.good,"governance":"PENDING"})["reason"],"PROMOTION_NOT_VERIFIED")

    def test_missing_source_evidence_is_blocked(self):
        self.promote()
        self.assertEqual(decide_persona_revision(self.old,self.new,{**self.good,"source_event_ids":[]})["reason"],"SOURCE_EVIDENCE_MISSING")

    def test_no_durable_delta_is_blocked(self):
        self.promote()
        self.new["current_self"]=self.old["current_self"]
        self.assertEqual(decide_persona_revision(self.old,self.new,self.good)["reason"],"NO_DURABLE_SELF_DELTA")

    def test_parent_mismatch_is_blocked(self):
        self.promote()
        self.new["parent_ir_id"]="mio-r70"
        self.assertEqual(decide_persona_revision(self.old,self.new,self.good)["reason"],"PARENT_REVISION_MISMATCH")

    def test_multiple_promotions_require_separate_review(self):
        self.promote()
        self.new["promoted_growth"].append({"growth_ref":"g3","status":"adopted"})
        self.assertFalse(decide_persona_revision(self.old,self.new,self.good)["revision_allowed"])

    def test_reordered_growth_is_blocked(self):
        self.new["promoted_growth"]=[{"growth_ref":"g2","status":"adopted"},{"growth_ref":"g1","status":"adopted"}]
        self.assertFalse(decide_persona_revision(self.old,self.new,self.good)["revision_allowed"])


if __name__=="__main__":
    unittest.main()
