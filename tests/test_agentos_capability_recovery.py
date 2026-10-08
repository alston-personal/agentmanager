import unittest
from scripts.agentos_capability_recovery import lookup

class RecoveryLookupTest(unittest.TestCase):
    def test_historical_image_publish_is_discoverable(self):
        rows=lookup("social.threads.publish.image")
        self.assertEqual(len(rows),1)
        entry=rows[0]["capability"]
        self.assertEqual(entry["verified_evidence"]["run_id"],35495831674)
        self.assertEqual(entry["verified_evidence"]["object_id"],"18356065492302036")
        self.assertEqual(entry["migration"]["status"],"not_integrated")
        self.assertIn("image_url",entry["legacy_contract"]["request_fields"])
        self.assertIn("no_text_only_fallback",entry["legacy_contract"]["requires"])
    def test_unknown_capability_not_fabricated(self):
        self.assertEqual(lookup("unknown.capability"),[])

if __name__=="__main__": unittest.main()
