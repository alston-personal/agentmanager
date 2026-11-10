import unittest
import hashlib
from agentos_node.social.post_experiment import CheckpointPolicy, build_snapshot, learning_record, next_observation

class SocialPostExperimentTests(unittest.TestCase):
    def test_three_accounts_share_same_policy(self):
        p=CheckpointPolicy()
        for account in ('mio.milkcat','oursong_alston','huang_alston'):
            snap=build_snapshot(experiment_id='x',account_username=account,post={'id':'123'},replies=[],previous_reply_ids=set(),captured_at='2026-09-27T00:00:00Z')
            self.assertEqual(next_observation(p,elapsed_minutes=60,snapshot=snap)['next_elapsed_minutes'],360)

    def test_attention_fast_follows(self):
        snap=build_snapshot(experiment_id='x',account_username='mio.milkcat',post={'id':'123'},replies=[{'id':'9','text':'hi'}],previous_reply_ids=set(),captured_at='2026-09-27T00:00:00Z')
        self.assertTrue(snap['needs_attention'])
        self.assertEqual(next_observation(CheckpointPolicy(),elapsed_minutes=60,snapshot=snap)['next_elapsed_minutes'],180)

    def test_learning_keeps_raw_and_derived_separate(self):
        snap=build_snapshot(experiment_id='x',account_username='huang_alston',post={'id':'123','text':'a'},replies=[],previous_reply_ids=set(),captured_at='2026-09-27T00:00:00Z')
        rec=learning_record(snap,elapsed_minutes=60,hypothesis='short hook works',changed_variables=['hook'])
        self.assertEqual(rec['schema'],'agentos.social-post-learning-observation/v1')
        self.assertEqual(rec['changed_variables'],['hook'])

    def test_caption_hash_exact_unicode_newline_and_missing_data(self):
        caption="早安，澪！\n🌿 今天有一點新的發現。"
        snap=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":caption},replies=[],previous_reply_ids=set(),
            captured_at="2026-11-10T00:00:00Z")
        self.assertEqual(snap["post"]["caption_sha256"],
            hashlib.sha256(caption.encode("utf-8")).hexdigest())
        different=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":caption.replace("\\n"," ")},replies=[],
            previous_reply_ids=set(),captured_at="2026-11-10T00:00:00Z")
        self.assertNotEqual(snap["post"]["caption_sha256"],different["post"]["caption_sha256"])
        empty=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":None},replies=[],previous_reply_ids=set(),
            captured_at="2026-11-10T00:00:00Z")
        self.assertIsNone(empty["post"]["caption_sha256"])

    def test_insights_cannot_auto_approve_mio_growth_rule(self):
        snap=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":"一則正式貼文"},replies=[],previous_reply_ids=set(),
            captured_at="2026-11-10T00:00:00Z")
        rec=learning_record(snap,elapsed_minutes=1470,
            observed_metrics={"views":125,"likes":6},insights_status="pass",
            hypothesis="早上表現較好",changed_variables=["publish_time","format"])
        self.assertEqual(rec["maturity"],"developing")
        self.assertEqual(rec["analysis_status"],"candidate")
        self.assertTrue(rec["source_evidence_ready"])
        self.assertFalse(rec["analysis_eligible"])
        self.assertFalse(rec["causal_claim_allowed"])
        self.assertEqual(rec["caption_sha256"],snap["post"]["caption_sha256"])
        self.assertEqual(rec["metric_precision"]["views"],"provider_unverified")

    def test_unavailable_insights_and_unknown_metrics_are_not_evidence(self):
        snap=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":"範例"},replies=[],previous_reply_ids=set(),
            captured_at="2026-11-10T00:00:00Z")
        unavailable=learning_record(snap,elapsed_minutes=60,
            observed_metrics={"views":21},insights_status="unavailable")
        self.assertEqual(unavailable["maturity"],"early")
        self.assertFalse(unavailable["source_evidence_ready"])
        self.assertFalse(unavailable["analysis_eligible"])
        nested=learning_record(snap,elapsed_minutes=10080,
            observed_metrics={"views":{"value":"20"}},insights_status="pass")
        self.assertEqual(nested["maturity"],"mature")
        self.assertEqual(nested["metrics"]["views"],{"value":"20"})
        self.assertFalse(nested["source_evidence_ready"])

    def test_negative_time_cannot_be_used_as_mature_evidence(self):
        snap=build_snapshot(experiment_id="x",account_username="mio.milkcat",
            post={"id":"p1","text":"x"},replies=[],previous_reply_ids=set(),
            captured_at="2026-11-10T00:00:00Z")
        with self.assertRaises(ValueError):
            learning_record(snap,elapsed_minutes=-1)

if __name__=='__main__': unittest.main()
