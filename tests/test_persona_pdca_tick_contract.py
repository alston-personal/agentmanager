import os
import unittest

os.environ.setdefault("AGENTOS_PERSONA_SLUG", "oursong_alstonhuang")
os.environ.setdefault("AGENTOS_PERSONA_ID", "oursong-alstonhuang-001")
os.environ.setdefault("AGENTOS_PERSONA_WRITE_PREFIX", "oursong")

from scripts import persona_pdca_tick_user as tick


class PersonaPDCATickContractTests(unittest.TestCase):
    def test_unresolved_reply_review_detected(self):
        state={"pending_external_actions":[
            {"capability":"social.reply.review","status":"completed","action_id":"old"},
            {"capability":"social.reply.review","status":"candidate","action_id":"current"},
        ]}
        self.assertEqual(tick.unresolved_reply_review(state)["action_id"],"current")

    def test_completed_reply_review_does_not_block_new_cycle(self):
        state={"pending_external_actions":[
            {"capability":"social.reply.review","status":"completed","action_id":"old"},
        ]}
        self.assertIsNone(tick.unresolved_reply_review(state))


if __name__=="__main__":
    unittest.main()
