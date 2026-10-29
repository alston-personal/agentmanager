import unittest
from scripts.persona_social_executor import select_reconciliation_fair_action


class SocialReconciliationFairness(unittest.TestCase):
    def test_held_reply_cannot_starve_observation(self):
        held={"action_id":"old-reply","status":"in_progress","capability":"social.reply.send",
              "reconciliation_required":True}
        read={"action_id":"new-read","status":"candidate","capability":"social.threads.observe"}
        self.assertIs(select_reconciliation_fair_action(held,[read],319),read)
        self.assertIs(select_reconciliation_fair_action(held,[read],320),held)

    def test_held_reply_still_reconciles_without_due_read(self):
        held={"action_id":"old-reply","capability":"social.reply.send"}
        self.assertIs(select_reconciliation_fair_action(held,[],319),held)


if __name__=="__main__":
    unittest.main()
