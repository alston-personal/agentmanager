"""#1825 outward public-root reply gate: offline, no platform writes."""
import hashlib
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

    def candidates(self, *, event=None, source=None, policy=True, events=None, reserved=None, approved_identity=False):
        self.file.write_text(json.dumps(self.source if source is None else source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        gate = {"proactive_external_reply_authorized": policy}
        if approved_identity:
            gate["approved_parent_identity_receipt_sha256"] = [
                hashlib.sha256(self.search_file.read_bytes()).hexdigest()]
        return self.m.external_reply_candidates(
            self.root, [self.event if event is None else event] if events is None else events,
            {"reply_decisions": {}}, {"source_sha256": "irsha"},
            gate, set() if reserved is None else reserved, self.now
        )

    def test_existing_receipts_project_into_in_memory_outward_event(self):
        self.source["platform"] = "threads"
        self.search["platform"] = "threads"
        self.file.write_text(json.dumps(self.source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        gate = {"proactive_external_reply_authorized": True,
                "approved_parent_identity_receipt_sha256": [
                    hashlib.sha256(self.search_file.read_bytes()).hexdigest()]}
        self.assertEqual(self.m.project_external_verified_events(
            self.root, {"proactive_external_reply_authorized": True}, self.now), [])
        events = self.m.project_external_verified_events(self.root, gate, self.now)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["object_id"], "123456789")
        self.assertEqual(events[0]["source_receipt_ref"], self.ref)
        self.assertEqual(events[0]["search_receipt_ref"], self.search_ref)
        candidates, _ = self.m.external_reply_candidates(
            self.root, events, {"reply_decisions": {}}, {"source_sha256": "irsha"},
            {"proactive_external_reply_authorized": True}, set(), self.now)
        self.assertEqual(len(candidates), 1)

    def test_projector_rejects_unattested_or_unapproved_evidence(self):
        self.source["platform"] = "threads"
        self.search["platform"] = "threads"
        self.file.write_text(json.dumps(self.source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        project = lambda enabled: self.m.project_external_verified_events(
            self.root, {"proactive_external_reply_authorized": enabled}, self.now)
        self.assertEqual(project(False), [])
        self.search["result"]["items"][0]["is_reply_attested"] = False
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        self.assertEqual(project(True), [])
        self.search["result"]["items"][0]["is_reply_attested"] = True
        self.search["result"]["items"][0]["username"] = "mio.milkcat"
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        self.assertEqual(project(True), [])
        self.search["result"]["items"][0]["username"] = "other_author"
        self.search["completed_at"] = (self.now - timedelta(days=5)).isoformat()
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        self.assertEqual(project(True), [])

    def test_provider_attested_identity_is_an_alternate_read_receipt(self):
        self.source["platform"] = "threads"
        self.search["platform"] = "threads"
        self.search["operation"] = "parent_identity.read"
        self.search["capability"] = "social.threads.parent_identity.read"
        self.search["result"] = {"identity": {
            **self.search["result"]["items"][0], "root_post_id": "123456789",
            "provider_verified": True, "numeric_id_source": "provider"
        }}
        self.file.write_text(json.dumps(self.source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        events = self.m.project_external_verified_events(
            self.root, {"proactive_external_reply_authorized": True}, self.now)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["object_id"], "123456789")
        selected, _ = self.candidates(events=events, approved_identity=True)
        self.assertEqual(len(selected), 1)

    def test_identity_receipt_rejects_shortcode_and_unattested_root(self):
        self.search["operation"] = "parent_identity.read"
        self.search["capability"] = "social.threads.parent_identity.read"
        row = self.search["result"]["items"][0]
        row.update(root_post_id="123456789", provider_verified=True, numeric_id_source="provider")
        self.search["result"] = {"identity": row}
        self.assertEqual(self.candidates()[0], [])
        self.assertEqual(len(self.candidates(approved_identity=True)[0]), 1)
        for key, value in (
            ("id", "Example"), ("provider_verified", False),
            ("numeric_id_source", "shortcode"), ("root_post_id", "999"),
            ("is_reply_attested", False), ("is_reply", True)
        ):
            with self.subTest(key=key):
                prior = row[key]
                row[key] = value
                self.assertEqual(self.candidates(approved_identity=True)[0], [])
                row[key] = prior

    def test_self_declared_provider_verification_without_digest_is_rejected(self):
        self.search["operation"] = "parent_identity.read"
        self.search["capability"] = "social.threads.parent_identity.read"
        self.search["result"] = {"identity": {
            **self.search["result"]["items"][0], "root_post_id": "123456789",
            "provider_verified": True, "numeric_id_source": "provider"
        }}
        self.file.write_text(json.dumps(self.source), encoding="utf-8")
        self.search_file.write_text(json.dumps(self.search), encoding="utf-8")
        self.assertEqual(self.candidates()[0], [])
        self.assertEqual(self.m.project_external_verified_events(
            self.root, {"proactive_external_reply_authorized": True}, self.now), [])
        gate = {"proactive_external_reply_authorized": True,
                "approved_parent_identity_receipt_sha256": ["0"*64]}
        self.assertEqual(self.m.project_external_verified_events(self.root, gate, self.now), [])

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

    def test_search_binding_permalink_text_and_receipt_freshness(self):
        original = json.loads(json.dumps(self.search))
        for field, value in (("account_binding_id", "other-account"),):
            self.search[field] = value
            self.assertEqual(self.candidates()[0], [])
            self.search = json.loads(json.dumps(original))
        for field, value in (("permalink", "https://www.threads.com/@different/post/X"),
                             ("text", "unrelated content")):
            self.search["result"]["items"][0][field] = value
            self.assertEqual(self.candidates()[0], [])
            self.search = json.loads(json.dumps(original))
        self.search["completed_at"] = (self.now - timedelta(days=5)).isoformat()
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
