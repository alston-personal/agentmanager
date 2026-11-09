import unittest
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

if __name__=='__main__': unittest.main()
