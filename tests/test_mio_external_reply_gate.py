"""#1825 outward public-root reply gate: offline, no platform writes."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/persona_reply_intent_generator.py"


def load_generator():
    # Pure selection unit: do not initialize a provider or load credentials.
    reasoning = types.ModuleType("persona_post_intent_generator")
    executor = types.ModuleType("persona_social_executor")
    executor.save = lambda *a, **kw: None
    executor.timestamp = lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")) if isinstance(v, str) else None
    with patch.dict(sys.modules, {
        "persona_post_intent_generator": reasoning,
        "persona_social_executor": executor,
    }):
        spec = importlib.util.spec_from_file_location("mio_reply_gate_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ExternalReplyGateTest(unittest.TestCase):
    def setUp(self):
        self.m = load_generator()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 11, 1, 0, tzinfo=timezone.utc)
        self.ref = "pdca/social_receipts/verified_123.json"
        self.search_ref = "pdca/social_receipts/search_123.json"
        file = self.root / self.ref
        file.parent.mkdir(parents=True)
        self.source = {
            "schema": "agentos.social-receipt/v1", "ok": True,
            "completed_at": self.now.isoformat().replace("+00:00", "Z"),
            "operation": "public_post.read", "platform_object_id": "123456789",
            "account_binding_id": "mio-bound-opaque",
            "result": {"source": {
                "username": "other_author", "visibility": "public",
                "root_post_id": "123456789",
                "url": "https://www.threads.com/@other_author/post/Example",
                "text": "公開討論內容"
            }}
        }
        self.file = file
        self.search = {
            "schema": "agentos.social-receipt/v1", "ok": True,
            "operation": "keyword.search", "completed_at": self.now.isoformat().replace("+00:00","Z"),
            "account_binding_id": "mio-bound-opaque",
            "result": {"items": [{"id": "123456789", "username": "other_author",
                "permalink": "https://www.threads.com/@other_author/post/Example",
                "text": "公開討論內容", "is_reply": False, "is_reply_attested": True}]}
        }
        self.search_file = self.root / self.search_ref
        self.event = {
            "type": "public.post.verified", "object_id": "123456789",
            "root_post_id": "123456789", "reader_account": "mio.milkcat",
            "author_handle": "other_author", "text": "公開討論內容",
            "source_url": "https://www.threads.com/@other_author/post/Example",
            "source_receipt_ref": self.ref, "search_receipt_ref": self.search_ref,
            "account_binding_id": "mio-bound-opaque",
            "timestamp": self.now.isoformat().replace("+00:00", "Z")
        }

    def candidates(self, *, event=None, source=None, policy=True, events=None, reserved=None):
        self.file.write_text(json.dumps(self.source if source is None else source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        return self.m.external_reply_candidates(
            self.root, [self.event if event is None else event] if events is None else events,
            {"reply_decisions": {}}, {"source_sha256": "irsha"},
            {"proactive_external_reply_authorized": policy},
            set() if reserved is None else reserved, self.now
        )

    def test_verified_root_is_candidate_not_a_write(self):
        items, skipped = self.candidates()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reply_id"], "123456789")
        self.assertTrue(items[0]["external_root"])

    def test_default_authority_is_fail_closed(self):
        items, skipped = self.candidates(policy=False)
        self.assertEqual(items, [])
        self.assertIn("external_reply_not_authorized", skipped)

    def test_inbox_only_is_not_outward_candidate(self):
        items, _ = self.candidates(events=[{**self.event, "type": "external.observation",
                                                "source_receipt_ref": None}])
        self.assertEqual(items, [])

    def test_unverified_parent_or_mismatched_receipt(self):
        for edits in ({"platform_object_id": "999"}, {"ok": False},
                      {"operation": "post.read"}, {"account_binding_id": "oursong-binding"}):
            with self.subTest(edits=edits):
                source = {**self.source, **edits}
                self.assertEqual(self.candidates(source=source)[0], [])

    def test_root_id_and_fresh_receipt_are_independently_required(self):
        self.assertEqual(self.candidates(event={**self.event, "root_post_id": "222"})[0], [])
        self.assertEqual(self.candidates(source={**self.source, "completed_at":
            (self.now - timedelta(days=6)).isoformat()})[0], [])
        self.assertEqual(self.candidates(event={**self.event, "timestamp":
            (self.now - timedelta(minutes=10)).isoformat()})[0], [])

    def test_search_correlates_platform_id_and_attested_nonreply(self):
        self.search["result"]["items"][0]["id"] = "999"
        self.assertEqual(self.candidates()[0], [])
        self.search["result"]["items"][0]["id"] = "123456789"
        self.search["result"]["items"][0]["is_reply_attested"] = False
        self.assertEqual(self.candidates()[0], [])
        self.search["result"]["items"][0]["is_reply_attested"] = True
        self.search["result"]["items"][0]["is_reply"] = True
        self.assertEqual(self.candidates()[0], [])

    def test_wrong_reader_or_canonical_url(self):
        for edits in ({"reader_account": "oursong_alstonhuang"},
                      {"source_url": "https://www.threads.com/@another/post/X"},
                      {"object_id": "not-a-number"}):
            with self.subTest(edits=edits):
                self.assertEqual(self.candidates(event={**self.event, **edits})[0], [])

    def test_stale_reserved_and_already_replied(self):
        stale = {**self.event, "timestamp": (self.now - timedelta(days=5)).isoformat()}
        self.assertEqual(self.candidates(event=stale)[0], [])
        self.assertEqual(self.candidates(reserved={"123456789"})[0], [])
        reply = {"type": "reply.sent", "parent_object_id": "123456789"}
        self.assertEqual(self.candidates(events=[self.event, reply])[0], [])

    def test_missing_source_and_path_traversal(self):
        bad = {**self.event, "source_receipt_ref": "../outside.json"}
        self.assertEqual(self.candidates(event=bad)[0], [])
        self.file.unlink()
        self.assertEqual(self.m.external_reply_candidates(
            self.root, [self.event], {}, {"source_sha256": "x"},
            {"proactive_external_reply_authorized": True}, set(), self.now
        )[0], [])


if __name__ == "__main__":
    unittest.main()
