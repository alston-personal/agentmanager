import unittest
from scripts.persona_social_discovery_triage import triage_public_discovery


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.projection={"schema":"agentos.persona-public-discovery/v1","status":"PASS",
                         "account":"mio.milkcat","write_allowed":False,
                         "items":[{"post_id":"123","author":"otherperson","text_excerpt":"週末去散步看到貓",
                                   "decision":"UNDECIDED","reply_allowed":False},
                                  {"post_id":"456","author":"friend","text_excerpt":"穿搭與裙子",
                                   "decision":"UNDECIDED","reply_allowed":False}]}
    def test_new_people_first_without_reply_authority(self):
        result=triage_public_discovery(self.projection,visited_authors=["friend"])
        self.assertEqual(result["items"][0]["author"],"otherperson")
        self.assertFalse(result["write_allowed"])
        self.assertFalse(result["items"][0]["reply_allowed"])
    def test_existing_interaction_is_not_spammed(self):
        result=triage_public_discovery(self.projection,contacted_posts=["123"])
        self.assertEqual(len(result["items"]),1)
    def test_blocklist_prevents_interaction_candidate(self):
        result=triage_public_discovery(self.projection,blocklisted_authors=["otherperson"])
        self.assertEqual(result["items"][0]["author"],"friend")
    def test_unrelated_posts_not_forced_into_engagement(self):
        self.projection["items"][0]["text_excerpt"]="12345"
        result=triage_public_discovery(self.projection)
        self.assertEqual(len(result["items"]),1)
    def test_unverified_projection_is_blocked(self):
        self.projection["status"]="BLOCKED"
        self.assertEqual(triage_public_discovery(self.projection)["status"],"BLOCKED")
    def test_fake_reply_authority_is_not_accepted(self):
        self.projection["items"][0]["reply_allowed"]=True
        self.assertEqual(len(triage_public_discovery(self.projection)["items"]),1)
    def test_bounded_memory(self):
        with self.assertRaises(ValueError):
            triage_public_discovery(self.projection,visited_authors=["x"]*5001)
    def test_no_discovered_candidates_is_valid(self):
        self.projection["items"]=[]
        self.assertEqual(triage_public_discovery(self.projection)["candidate_count"],0)
if __name__=="__main__":
    unittest.main()
