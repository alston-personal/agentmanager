"""Offline executor regressions: an unready image must not consume reply turns."""
import contextlib
import copy
import io
import json
import sys
import unittest
from unittest.mock import patch

from tests import test_persona_media_publish as fixtures


class SocialSelection(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.MediaLane("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.social = fixtures.social
        self.reply = {"action_id": "reply-after-image", "status": "candidate",
                      "capability": "social.reply.send", "primary_text": "這個角度很有趣。",
                      "reply_to_id": "456", "root_post_id": "789"}
        self.f.state["pending_external_actions"].append(self.reply)
        self.env = self.f.root / "runtime.env"
        self.env.write_text('AGENTOS_SOCIAL_PRODUCTS_JSON={"galaxy":{"api_key":"offline"}}\n'
                            'AGENTOS_SOCIAL_CONTROL_TOKEN=offline\n')
        self.creds = self.f.write("creds.json", {"bindings": {"binding-123": {
            "platform": "threads", "product_id": "galaxy", "username": "mio.milkcat",
            "provider_account_id": "123", "auth_profile": "persona"}}})
        self.calls = []

    def adapter(self, path, request, headers, timeout=20):
        self.calls.append((path, copy.deepcopy(request)))
        if path == "/internal/v1/social/acceptances":
            self.assertEqual(request["operation"], "reply")
            self.assertNotIn("image_url", request)
            return 201, {"acceptance_id": "offline-reply"}
        if path == "/v1/social/reply":
            self.assertEqual(request["reply_to_id"], "456")
            return 200, {"ok": True, "platform_object_id": "321"}
        raise AssertionError("Unexpected adapter operation: " + path)

    def execute(self, adapter=None):
        with patch.object(self.social, "ENV", self.env), patch.object(self.social, "CREDS", self.creds), \
             patch.object(self.social, "post", adapter or self.adapter), \
             patch.object(fixtures.assets, "read_public_image", self.f.public), \
             patch.object(sys, "argv", ["social", "--persona-dir", str(self.f.root),
                                       "--receipt-out", str(self.f.out)]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.social.main(), 0)
        return json.loads(self.f.out.read_text())

    def persist(self):
        self.f.write("pdca/state.json", self.f.state)

    def test_unready_image_does_not_block_due_reply(self):
        self.f.action["media_intent"]["status"] = "awaiting_asset_and_validation"
        before = copy.deepcopy(self.f.action)
        self.persist()
        receipt = self.execute()
        self.assertEqual(receipt["action_id"], self.reply["action_id"])
        self.assertEqual(receipt["status"], "EXECUTED")
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][0], before)
        self.assertEqual(state["pending_external_actions"][1]["status"], "completed")
        self.assertEqual(state["energy_current"], 2)
        event = json.loads((self.f.root / "events/events.jsonl").read_text())
        self.assertEqual((event["type"], event["parent_object_id"], event["root_post_id"]),
                         ("reply.sent", "456", "789"))
        self.assertEqual([p for p, _ in self.calls],
                         ["/internal/v1/social/acceptances", "/v1/social/reply"])

    def test_both_image_modes_and_failed_review_states_allow_due_reply(self):
        for mode in ("generate", "existing_verified"):
            for status in ("generated_unverified", "blocked"):
                with self.subTest(mode=mode, status=status):
                    self.f.action["media_intent"].update(mode=mode, status=status)
                    before = copy.deepcopy(self.f.action)
                    self.calls.clear()
                    (self.f.root / "events/events.jsonl").write_text("")
                    self.persist()
                    receipt = self.execute()
                    state = json.loads((self.f.root / "pdca/state.json").read_text())
                    self.assertEqual(receipt["action_id"], self.reply["action_id"])
                    self.assertEqual(state["pending_external_actions"][0], before)
                    self.assertEqual(state["energy_current"], 2)
                    self.assertEqual(len(self.calls), 2)

    def test_hold_never_becomes_text_post_or_repeats_completed_reply(self):
        self.f.action["media_intent"]["status"] = "blocked"
        self.persist()
        self.assertEqual(self.execute()["action_id"], self.reply["action_id"])
        receipt = self.execute()
        self.assertEqual(receipt["action_id"], self.f.action["action_id"])
        self.assertEqual((receipt["status"], receipt["write_performed"]), ("BLOCKED", False))
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][0]["status"], "candidate")
        self.assertEqual(state["pending_external_actions"][0]["media_intent"]["mode"], "generate")
        self.assertEqual(state["energy_current"], 2)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len((self.f.root / "events/events.jsonl").read_text().splitlines()), 1)

    def test_future_reply_is_not_sent_to_escape_image_hold(self):
        self.reply["not_before"] = "2100-01-01T00:00:00Z"
        self.persist()
        receipt = self.execute()
        self.assertEqual(receipt["action_id"], self.f.action["action_id"])
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertEqual(self.calls, [])
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][1], self.reply)
        self.assertEqual(state["energy_current"], 5)

    def test_observation_still_precedes_all_due_writes(self):
        observation = {"action_id": "observe-after-writes", "status": "candidate",
                       "capability": "social.threads.observe", "cycle": 10}
        self.f.state["pending_external_actions"].append(observation)
        self.persist()
        def read_adapter(path, request, headers, timeout=20):
            self.calls.append((path, request))
            self.assertEqual((path, request["operation"]), ("/v1/social/status", "post.read"))
            return 200, {"ok": True, "result": {"items": []}}
        receipt = self.execute(read_adapter)
        self.assertEqual((receipt["action_id"], receipt["read_status"]),
                         (observation["action_id"], "PASS"))
        self.assertFalse(receipt["write_performed"])
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][:2], [self.f.action, self.reply])
        self.assertEqual(state["energy_current"], 5)

    def test_validated_image_keeps_its_turn_and_exact_readback(self):
        self.f.ready()
        self.persist()
        receipt = self.execute(self.f.adapter)
        self.assertEqual(receipt["action_id"], self.f.action["action_id"])
        self.assertEqual(receipt["media_readback_status"], "PASS")
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][1], self.reply)
        self.assertEqual(state["energy_current"], -3)
        self.assertEqual([p for p, _ in self.f.calls].count("/v1/social/publish"), 1)

    def start_pending_image_write(self):
        self.f.ready()
        row = self.f.row
        self.f.row = None
        receipt = self.f.execute()
        self.assertEqual(receipt["status"], "AWAITING_READBACK")
        self.f.row = row

    def test_node_journal_preserves_reconciliation_after_failed_data_push(self):
        self.start_pending_image_write()
        # Recreate the stale candidate Git can retain when a data push fails.
        self.f.action["status"] = "candidate"
        self.f.action["media_intent"]["status"] = "blocked"
        self.f.action.pop("energy_debited")
        self.f.state["energy_current"] = 5
        self.persist()
        receipt = self.execute(self.f.adapter)
        self.assertEqual(receipt["action_id"], self.f.action["action_id"])
        self.assertEqual(receipt["media_readback_status"], "PASS")
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][1], self.reply)
        self.assertEqual(state["energy_current"], -3)
        self.assertEqual([p for p, _ in self.f.calls].count("/v1/social/publish"), 1)
        self.assertEqual([p for p, _ in self.f.calls].count("/internal/v1/social/acceptances"), 1)
        self.assertEqual(self.f.calls[-1][0], "/v1/social/status")

    def test_in_progress_image_keeps_read_only_reconciliation_at_negative_energy(self):
        self.start_pending_image_write()
        self.persist()
        receipt = self.execute(self.f.adapter)
        self.assertEqual(receipt["media_readback_status"], "PASS")
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][1], self.reply)
        self.assertEqual(state["energy_current"], -3)
        self.assertEqual([p for p, _ in self.f.calls].count("/v1/social/publish"), 1)

    def test_future_image_still_waits_while_due_reply_executes(self):
        self.f.action["not_before"] = "2100-01-01T00:00:00Z"
        self.persist()
        receipt = self.execute()
        self.assertEqual(receipt["action_id"], self.reply["action_id"])
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][0], self.f.action)

    def test_ordinary_text_post_keeps_fifo(self):
        self.f.action["media_intent"] = {"mode": "none"}
        self.persist()
        def text_adapter(path, request, headers, timeout=20):
            self.calls.append((path, request))
            self.assertEqual(request["operation"], "publish")
            self.assertNotIn("image_url", request)
            if path == "/internal/v1/social/acceptances":
                return 201, {"acceptance_id": "offline-post"}
            self.assertEqual(path, "/v1/social/publish")
            return 200, {"ok": True, "platform_object_id": "987"}
        receipt = self.execute(text_adapter)
        self.assertEqual(receipt["action_id"], self.f.action["action_id"])
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][1], self.reply)

    def test_reply_still_obeys_energy_gate(self):
        self.f.state["energy_current"] = 0
        self.persist()
        receipt = self.execute()
        self.assertEqual((receipt["action_id"], receipt["result"]),
                         (self.reply["action_id"], "ENERGY_DEPLETED"))
        self.assertFalse(receipt["write_performed"])
        self.assertEqual(self.calls, [])
        state = json.loads((self.f.root / "pdca/state.json").read_text())
        self.assertEqual(state["pending_external_actions"][0], self.f.action)
        self.assertEqual(state["energy_current"], 0)

    def test_empty_due_queue_does_not_touch_adapter(self):
        self.f.action["not_before"] = self.reply["not_before"] = "2100-01-01T00:00:00Z"
        self.persist()
        self.assertEqual(self.execute()["status"], "NO_ACTION")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
