import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import persona_social_executor as social


class ReplyIntentParity(unittest.TestCase):
    def test_unconfirmed_reply_does_not_stay_candidate_in_durable_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"pdca/reply_intents").mkdir(parents=True)
            (root/"pdca/social_receipts").mkdir(parents=True)
            aid="test-old-reply"
            intent=root/"pdca/reply_intents"/(aid+".json")
            intent.write_text(json.dumps({"action_id":aid,"capability":"social.reply.send",
                                          "status":"candidate"}))
            action={"action_id":aid,"capability":"social.reply.send",
                    "status":"in_progress","reply_to_id":"456","root_post_id":"789",
                    "primary_text":"Hello","reconciliation_required":True}
            state={"pending_external_actions":[action]}
            out=root/"pdca/social_receipts"/"test.json"
            with patch.object(social,"read_items",return_value=([],{})):
                receipt=social.reconcile_held_reply(root,state,action,out,{},{},"2026-10-17T10:31:00Z")
            durable=json.loads(intent.read_text())
            self.assertEqual(receipt["status"],"RECONCILIATION_PENDING")
            self.assertEqual(durable["status"],"in_progress")
            self.assertTrue(durable["reconciliation_required"])
            self.assertFalse(durable["write_replay_allowed"])
            self.assertFalse(receipt["write_performed"])


if __name__=="__main__":
    unittest.main()
