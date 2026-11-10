#!/usr/bin/env python3
"""
單元測試：Social Galaxy 多社群適配器與全功能圖譜引擎
Tests for Social Galaxy multi-platform adapters and graph analytics
"""
import unittest
from datetime import datetime, timezone

from agent_core.social_galaxy import (
    CanonicalSocialEvent,
    RelationshipGraph,
    IdentityResolver,
)
from agent_core.social_galaxy.adapters import (
    ThreadsAdapter,
    XAdapter,
    BlueskyAdapter,
    GenericSocialAdapter,
)


class TestSocialGalaxyAdapters(unittest.TestCase):
    def test_threads_adapter_parsing(self):
        adapter = ThreadsAdapter()
        raw = {
            "id": "18353956147218749",
            "username": "alston_dev",
            "replied_to_username": "mio_oracle",
            "is_quote_post": False,
            "event_type": "reply",
            "timestamp": "2026-11-10T08:00:00Z",
        }
        ev = adapter.parse_raw_event(raw)
        self.assertEqual(ev.source, "threads")
        self.assertEqual(ev.actor_id, "threads:alston_dev")
        self.assertEqual(ev.target_id, "threads:mio_oracle")
        self.assertEqual(ev.event_type, "reply")

    def test_x_adapter_parsing(self):
        adapter = XAdapter()
        raw = {
            "id": "192837465",
            "author_username": "alice_x",
            "in_reply_to_username": "bob_x",
            "type": "mention",
            "created_at": "2026-11-10T08:05:00Z",
        }
        ev = adapter.parse_raw_event(raw)
        self.assertEqual(ev.source, "x")
        self.assertEqual(ev.actor_id, "x:alice_x")
        self.assertEqual(ev.target_id, "x:bob_x")
        self.assertEqual(ev.event_type, "mention")

    def test_bluesky_adapter_parsing(self):
        adapter = BlueskyAdapter()
        raw = {
            "cid": "bafyreihdwdcefghijk",
            "uri": "at://did:plc:123/app.bsky.feed.post/456",
            "author": {"handle": "carol.bsky.social"},
            "reply": {"parent": {"author": {"handle": "dave.bsky.social"}}},
            "createdAt": "2026-11-10T08:10:00Z",
        }
        ev = adapter.parse_raw_event(raw)
        self.assertEqual(ev.source, "bluesky")
        self.assertEqual(ev.actor_id, "bluesky:carol.bsky.social")
        self.assertEqual(ev.target_id, "bluesky:dave.bsky.social")
        self.assertEqual(ev.event_type, "reply")

    def test_cross_platform_graph_convergence(self):
        """驗證跨平台事件能順利彙整進同一個關係宇宙並產出 S/A/B/C/D 評級與六軸輪廓。"""
        resolver = IdentityResolver()
        resolver.bind("threads:alston_dev", "entity:alston")
        resolver.bind("x:alston_tw", "entity:alston")
        resolver.bind("threads:mio_oracle", "entity:mio")
        resolver.bind("x:mio_tw", "entity:mio")

        now = datetime.now(timezone.utc).isoformat()
        events = [
            CanonicalSocialEvent(
                id="e1", source="threads",
                actor_id="threads:alston_dev", actor_name="@alston_dev",
                target_id="threads:mio_oracle", target_name="@mio_oracle",
                event_type="reply", timestamp=now, confidence=1.0,
            ),
            CanonicalSocialEvent(
                id="e2", source="x",
                actor_id="x:mio_tw", actor_name="@mio_tw",
                target_id="x:alston_tw", target_name="@alston_tw",
                event_type="quote", timestamp=now, confidence=1.0,
            ),
        ]

        resolved_events = [resolver.resolve_event(e) for e in events]
        graph = RelationshipGraph(self_id="entity:alston", days=30)
        res = graph.compute(resolved_events)

        self.assertEqual(res["self_id"], "entity:alston")
        self.assertEqual(len(res["nodes"]), 1)
        node_mio = res["nodes"][0]
        self.assertEqual(node_mio["id"], "entity:mio")
        self.assertTrue(node_mio["reciprocal"])  # 雙向互惠
        self.assertIn(node_mio["tier"], ["S", "A"])  # 高權重核心關係
        self.assertIn("influence", res["profile"])
        self.assertIn("reciprocity", res["profile"])


if __name__ == "__main__":
    unittest.main()
