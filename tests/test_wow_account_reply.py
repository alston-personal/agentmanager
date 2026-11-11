import unittest

from agentos_node.wow_account_reply import (
    encode_account_reply,
    decode_account_reply,
)
from agentos_node.wow_reply_slot import render_account_reply_slot


class AccountReplyTest(unittest.TestCase):
    def test_verified_public_identity_renders_only_labels(self):
        payload = {
            "status": "REALM_SELECTED",
            "signed_in": True,
            "account": "original@example.test",
            "realm": "realm-u-" + "a" * 24,
        }
        wire = encode_account_reply(18, payload)
        self.assertEqual(decode_account_reply(wire, expected_request_id=18), payload)
        slot = render_account_reply_slot(wire, expected_request_id=18).decode("ascii")
        self.assertIn('account = "original@example.test"', slot)
        self.assertIn('realm = "realm-u-' + "a"*24 + '"', slot)
        self.assertIn('signed_in = true', slot)
        self.assertNotIn("token", slot)
        self.assertNotIn("handle", slot)
        self.assertNotIn("RunScript", slot)

    def test_logout_clears_identity_and_realm(self):
        slot = render_account_reply_slot(encode_account_reply(19, {
            "status": "SIGNED_OUT", "signed_in": False, "account": None, "realm": None,
        }), expected_request_id=19).decode("ascii")
        self.assertIn("signed_in = false", slot)
        self.assertNotIn("account =", slot)
        self.assertNotIn("realm =", slot)

    def test_reject_mismatch_tokens_injection_and_forged_identity(self):
        valid = encode_account_reply(20, {
            "status": "SIGNED_IN", "signed_in": True,
            "account": "a@example.test", "realm": None,
        })
        with self.assertRaisesRegex(ValueError, "unmatched_account_reply"):
            decode_account_reply(valid, expected_request_id=21)
        for payload in (
            {"status": "SIGNED_IN", "signed_in": True, "account": "a@example.test", "realm": None, "access_token": "sensitive"},
            {"status": "SIGNED_OUT", "signed_in": False, "account": "a@example.test", "realm": None},
            {"status": "REALM_SELECTED", "signed_in": True, "account": 'a"; RunScript("evil")', "realm": "realm-u-"+"a"*24},
            {"status": "REALM_SELECTED", "signed_in": True, "account": "a@example.test", "realm": "arbitrary"},
            {"status": "SIGNED_IN", "signed_in": "true", "account": "a@example.test", "realm": None},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    encode_account_reply(20, payload)


if __name__ == "__main__":
    unittest.main()
