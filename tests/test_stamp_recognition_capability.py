import unittest

from capabilities.stamp_recognition import StampMatch, validate_match


class StampRecognitionContractTests(unittest.TestCase):
    def test_same_stamp_requires_stamp_id(self):
        with self.assertRaises(ValueError):
            validate_match(StampMatch(decision="same_stamp", score=0.98))

    def test_same_entity_new_stamp_requires_entity_id(self):
        with self.assertRaises(ValueError):
            validate_match(StampMatch(decision="same_entity_new_stamp", score=0.91))

    def test_confirmed_same_stamp_contract(self):
        validate_match(
            StampMatch(
                decision="same_stamp",
                score=0.99,
                stamp_id="stamp-1",
                entity_id="vendor-1",
                requires_confirmation=False,
                reasons=("visual fingerprint matched confirmed samples",),
            )
        )

    def test_uncertain_match_stays_confirmation_required(self):
        match=StampMatch(decision="uncertain", score=0.61)
        validate_match(match)
        self.assertTrue(match.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
