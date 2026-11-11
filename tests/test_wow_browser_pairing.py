from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.wow_account_pairing import (
    start_pairing, approve_pairing, poll_pairing, revoke_pairing, authorization_html,
)


class WowBrowserPairingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = "agentos.milkcat.org"
        self.now = 1700000000
        self.owner_realm = "realm-u-" + "1" * 24

    def start(self):
        status, result = start_pairing(host=self.host, root=self.root, now=self.now)
        self.assertEqual(status, 201, result)
        self.assertNotIn("auth_token", str(result))
        self.assertEqual(len(result["claim_secret"]), 64)
        self.assertIn("/wow/account/authorize?code=", result["verification_url"])
        return result

    def approve(self, code, *, identity="original@example.test", membership=True, origin="https://agentos.milkcat.org"):
        return approve_pairing(
            host=self.host, origin=origin, cookie="opaque-website-cookie", code=code,
            root=self.root, now=self.now,
            identity_reader=lambda **_: {"provider": "google", "subject": "owner-subject",
                                          "display_name": identity},
            membership_reader=lambda **_: (
                (200, {"ok": True, "realm_id": self.owner_realm}) if membership else
                (403, {"ok": False, "error": "realm_membership_required"})
            ),
        )

    def test_real_server_session_proof_is_required_before_bridge_can_see_realm(self):
        rec = self.start()
        code, secret = rec["code"], rec["claim_secret"]
        status, pending = poll_pairing(host=self.host, code=code, claim_secret=secret, root=self.root, now=self.now)
        self.assertEqual((status, pending["state"]), (200, "pending"))
        bad, _ = poll_pairing(host=self.host, code=code, claim_secret="0"*64, root=self.root, now=self.now)
        self.assertEqual(bad, 404)
        status, approved = self.approve(code)
        self.assertEqual((status, approved["state"]), (200, "approved"))
        status, result = poll_pairing(host=self.host, code=code, claim_secret=secret, root=self.root, now=self.now)
        self.assertEqual(status, 200)
        self.assertEqual(result["account"], "original@example.test")
        self.assertEqual(result["realm"], self.owner_realm)
        self.assertNotIn("claim_secret", str(self.root.joinpath(code + ".json").read_text()))
        self.assertNotIn("opaque-website-cookie", str(self.root.joinpath(code + ".json").read_text()))
        self.assertNotIn("owner-subject", str(self.root.joinpath(code + ".json").read_text()))
        status, _ = revoke_pairing(host=self.host, code=code, claim_secret=secret, root=self.root, now=self.now)
        self.assertEqual(status, 200)
        self.assertEqual(poll_pairing(host=self.host, code=code, claim_secret=secret, root=self.root, now=self.now)[0], 404)

    def test_no_identity_or_membership_no_pairing(self):
        rec = self.start()
        denied, result = self.approve(rec["code"], membership=False)
        self.assertEqual((denied, result["error"]), (403, "realm_membership_required"))
        state = poll_pairing(host=self.host, code=rec["code"], claim_secret=rec["claim_secret"], root=self.root, now=self.now)[1]
        self.assertEqual(state["state"], "pending")

    def test_wrong_origin_and_host_rejected(self):
        rec = self.start()
        self.assertEqual(self.approve(rec["code"], origin="https://evil.example")[0], 403)
        self.assertEqual(start_pairing(host="studio.milkcat.org", root=self.root, now=self.now)[0], 400)
        self.assertEqual(poll_pairing(host="studio.milkcat.org", code=rec["code"], claim_secret=rec["claim_secret"], root=self.root, now=self.now)[0], 400)

    def test_expired_pairing_cannot_be_approved_or_polled(self):
        rec = self.start()
        self.assertEqual(poll_pairing(host=self.host, code=rec["code"], claim_secret=rec["claim_secret"], root=self.root, now=self.now + 601)[0], 404)
        self.assertEqual(approve_pairing(
            host=self.host, origin="https://agentos.milkcat.org", cookie="cookie",
            code=rec["code"], root=self.root, now=self.now + 601,
            identity_reader=lambda **_: {"display_name": "test"},
            membership_reader=lambda **_: (200, {"ok": True, "realm_id": self.owner_realm}),
        )[0], 410)

    def test_browser_requires_actual_agentos_login(self):
        rec = self.start()
        status, markup = authorization_html(host=self.host, code=rec["code"], cookie=None, root=self.root,
            now=self.now, identity_reader=lambda **_: None)
        self.assertEqual(status, 200)
        self.assertIn("site=agentos", markup)
        self.assertNotIn(rec["claim_secret"], markup)
        status, markup = authorization_html(host=self.host, code=rec["code"], cookie="cookie", root=self.root,
            now=self.now, identity_reader=lambda **_: {"display_name": "<example>"})
        self.assertEqual(status, 200)
        self.assertIn("&lt;example&gt;", markup)
        self.assertNotIn("<example>", markup)
        self.assertIn("Approve this account", markup)
        self.assertNotIn(rec["claim_secret"], markup)

    def test_reject_unsupported_legacy_realm_and_spoofed_oauth_subject(self):
        rec = self.start()
        status, result = approve_pairing(host=self.host, origin="https://agentos.milkcat.org",
            cookie="cookie", code=rec["code"], root=self.root, now=self.now,
            identity_reader=lambda **_: {"display_name": "attacker"},
            membership_reader=lambda **_: (200, {"ok": True, "realm_id": "realm-alston"}))
        self.assertEqual((status, result["error"]), (403, "unsupported_realm"))


if __name__ == "__main__":
    unittest.main()
