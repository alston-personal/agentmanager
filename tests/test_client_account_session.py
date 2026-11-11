import unittest

from agentos_node.client_account_session import AccountSessionBoundary


class AccountSessionBoundaryTest(unittest.TestCase):
    def make_broker(self):
        events = []
        def start():
            events.append(("begin",))
            return {"ticket": "ticket-12345678"}
        def redeem(ticket):
            events.append(("redeem", ticket))
            return {"handle": "handle-12345678", "account": "user@example.test"}
        def member(handle, realm):
            events.append(("membership", handle, realm))
            return realm == "realm-u-" + "1" * 24
        def revoke(handle):
            events.append(("revoke", handle))
            return True
        return AccountSessionBoundary(start, redeem, member, revoke), events

    def test_account_login_realm_and_logout_do_not_touch_node(self):
        broker, events = self.make_broker()
        self.assertEqual(broker.public_status(), {"signed_in": False, "account": None, "realm": None})
        self.assertEqual(broker.begin_login()["status"], "PAIRING_STARTED")
        self.assertEqual(broker.complete_login("wrong")["status"], "UNAUTHORIZED")
        self.assertEqual(broker.complete_login("ticket-12345678")["status"], "SIGNED_IN")
        old_realm = "realm-u-" + "1" * 24
        self.assertEqual(broker.choose_realm(old_realm)["status"], "REALM_SELECTED")
        self.assertEqual(broker.public_status()["realm"], old_realm)
        self.assertEqual(broker.choose_realm("realm-u-" + "2" * 24)["status"], "REALM_FORBIDDEN")
        self.assertIsNone(broker.public_status()["realm"])
        self.assertEqual(broker.sign_out()["status"], "SIGNED_OUT")
        self.assertFalse(broker.public_status()["signed_in"])
        self.assertIn(("revoke", "handle-12345678"), events)
        self.assertNotIn("node_token", str(broker.public_status()))
        self.assertNotIn("handle-12345678", str(broker.public_status()))

    def test_wrong_ticket_never_redeemed(self):
        broker, events = self.make_broker()
        self.assertEqual(broker.complete_login("ticket-12345678")["status"], "UNAUTHORIZED")
        self.assertEqual(events, [])
        broker.begin_login()
        self.assertEqual(broker.complete_login("wrong")["status"], "UNAUTHORIZED")
        self.assertEqual(events, [("begin",)])

    def test_revoke_failure_clears_local_and_reports_uncertain(self):
        broker = AccountSessionBoundary(
            lambda: {"ticket": "ticket-12345678"},
            lambda _: {"handle": "handle-12345678", "account": "user@example.test"},
            lambda *_: True,
            lambda _: False,
        )
        broker.begin_login()
        broker.complete_login("ticket-12345678")
        self.assertEqual(broker.sign_out()["status"], "REVOCATION_UNCONFIRMED")
        self.assertFalse(broker.public_status()["signed_in"])
        self.assertEqual(broker.choose_realm("realm-u-" + "1" * 24)["status"], "SIGN_IN_REQUIRED")

    def test_no_callback_can_claim_membership_with_truthy_string(self):
        broker = AccountSessionBoundary(
            lambda: {"ticket": "ticket-12345678"},
            lambda _: {"handle": "handle-12345678", "account": "user@example.test"},
            lambda *_: "true",
            lambda _: True,
        )
        broker.begin_login()
        broker.complete_login("ticket-12345678")
        self.assertEqual(broker.choose_realm("realm-u-" + "1" * 24)["status"], "REALM_FORBIDDEN")
        self.assertIsNone(broker.public_status()["realm"])

    def test_bad_pairing_and_token_shaped_extras_rejected(self):
        broker = AccountSessionBoundary(
            lambda: {"ticket": "ticket-12345678", "access_token": "secret"},
            lambda _: {},
            lambda *_: True,
            lambda _: True,
        )
        with self.assertRaisesRegex(ValueError, "pairing_must_remain_host_side"):
            broker.begin_login()

    def test_relogin_replaces_account_not_node(self):
        identity = iter(["first@example.test", "second@example.test"])
        handles = iter(["handle-12345678", "handle-87654321"])
        broker = AccountSessionBoundary(
            lambda: {"ticket": "ticket-12345678"},
            lambda _: {"handle": next(handles), "account": next(identity)},
            lambda *_: True,
            lambda _: True,
        )
        for expected in ("first@example.test", "second@example.test"):
            broker.begin_login()
            broker.complete_login("ticket-12345678")
            self.assertEqual(broker.public_status()["account"], expected)
            self.assertEqual(broker.sign_out()["status"], "SIGNED_OUT")


if __name__ == "__main__":
    unittest.main()
