"""Offline WoW pixel-to-Node-account contract; no real OAuth, game or ONE."""
from __future__ import annotations

import json
import unittest

from agentos_node.client_account_session import AccountSessionBoundary
from agentos_node.wow_account_intent_bridge import WoWAccountIntentBridge
from agentos_node.wow_bridge_protocol import encode


def packet(action: str, sequence: int) -> list[int]:
    return encode(sequence, json.dumps({"action": action, "session": "game12345"}).encode())


class AccountBridgeOfflineTest(unittest.TestCase):
    def test_two_accounts_same_node_without_node_rebind(self):
        identities = iter([("handle-first-123456", "test@example.test"),
                           ("handle-second-12345", "original@example.test")])
        memberships = {"realm-u-" + "1" * 24: "handle-first-123456",
                       "realm-u-" + "2" * 24: "handle-second-12345"}
        state = {"pairing": 0, "revocations": []}
        def start_pairing():
            state["pairing"] += 1
            return {"ticket": "ticket-" + str(state["pairing"]).zfill(12)}
        def redeem(_):
            handle, account = next(identities)
            return {"handle": handle, "account": account}
        def member(handle, realm):
            return memberships.get(realm) == handle
        def revoke(handle):
            state["revocations"].append(handle)
            return True
        account = AccountSessionBoundary(start_pairing, redeem, member, revoke)
        bridge = WoWAccountIntentBridge(account=account, capture_authorized=lambda: True)
        original_node = {"node_id": "same-physical-node", "realm_id": "unchanged-node-realm"}
        self.assertEqual(bridge.accept_capture(packet("wow.account.login.start", 1))["status"], "PAIRING_STARTED")
        self.assertEqual(account.complete_login("ticket-000000000001")["status"], "SIGNED_IN")
        self.assertEqual(account.choose_realm("realm-u-" + "1" * 24)["status"], "REALM_SELECTED")
        self.assertEqual(bridge.public_account()["account"], "test@example.test")
        self.assertEqual(bridge.accept_capture(packet("wow.account.logout", 2))["status"], "SIGNED_OUT")
        self.assertIsNone(bridge.public_account()["realm"])
        self.assertEqual(bridge.accept_capture(packet("wow.account.login.start", 3))["status"], "PAIRING_STARTED")
        self.assertEqual(account.complete_login("ticket-000000000002")["status"], "SIGNED_IN")
        self.assertEqual(account.choose_realm("realm-u-" + "1" * 24)["status"], "REALM_FORBIDDEN")
        self.assertEqual(account.choose_realm("realm-u-" + "2" * 24)["status"], "REALM_SELECTED")
        self.assertEqual(bridge.public_account()["account"], "original@example.test")
        self.assertEqual(bridge.public_account()["realm"], "realm-u-" + "2" * 24)
        self.assertEqual(original_node["realm_id"], "unchanged-node-realm")
        self.assertEqual(state["revocations"], ["handle-first-123456"])
        self.assertNotIn("handle-second-12345", str(bridge.public_account()))

    def test_denied_capture_cannot_logout_or_start_browser(self):
        activity = []
        account = AccountSessionBoundary(
            lambda: activity.append("browser") or {"ticket": "ticket-12345678"},
            lambda _: {"handle": "handle-12345678", "account": "x@example.test"},
            lambda *_: True,
            lambda _: activity.append("revoke") or True,
        )
        bridge = WoWAccountIntentBridge(account=account, capture_authorized=lambda: False)
        self.assertEqual(bridge.accept_capture(packet("wow.account.login.start", 7))["reason"], "BRIDGE_NOT_AUTHORIZED")
        self.assertEqual(bridge.accept_capture(packet("wow.account.logout", 8))["reason"], "BRIDGE_NOT_AUTHORIZED")
        self.assertEqual(activity, [])
        self.assertFalse(bridge.public_account()["signed_in"])

    def test_replay_does_not_repeat_login_or_logout(self):
        events = []
        account = AccountSessionBoundary(
            lambda: events.append("begin") or {"ticket": "ticket-12345678"},
            lambda _: {"handle": "handle-12345678", "account": "x@example.test"},
            lambda *_: True,
            lambda _: events.append("revoke") or True,
        )
        bridge = WoWAccountIntentBridge(account=account, capture_authorized=lambda: True)
        request = packet("wow.account.login.start", 21)
        self.assertEqual(bridge.accept_capture(request)["status"], "PAIRING_STARTED")
        self.assertEqual(bridge.accept_capture(request)["reason"], "DUPLICATE_REQUEST")
        self.assertEqual(events, ["begin"])


if __name__ == "__main__":
    unittest.main()
