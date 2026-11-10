#!/usr/bin/env python3
"""
單元測試：Social Relationship Galaxy 跨社群通用架構與合約驗證
Tests for Social Relationship Galaxy multi-platform decoupling contracts
"""
import unittest
from datetime import datetime, timezone


class TestSocialGalaxyContracts(unittest.TestCase):
    def test_canonical_social_event_structure(self):
        """驗證標準社群事件 (Canonical Social Event) 具備平台無關性。"""
        # 測試跨平台事件實例 (Threads, X/Twitter, Bluesky, Mastodon)
        events = [
            {
                "id": "threads:reply:12345",
                "source": "threads",
                "actor_id": "threads:alice",
                "actor_name": "@alice",
                "target_id": "threads:bob",
                "target_name": "@bob",
                "event_type": "reply",
                "timestamp": "2026-11-10T08:00:00Z",
                "confidence": 1.0,
                "meta": {"post_id": "p100"},
            },
            {
                "id": "x:mention:67890",
                "source": "x",
                "actor_id": "x:carol",
                "actor_name": "@carol",
                "target_id": "x:alice",
                "target_name": "@alice",
                "event_type": "mention",
                "timestamp": "2026-11-10T08:05:00Z",
                "confidence": 0.9,
                "meta": {"tweet_id": "t200"},
            },
            {
                "id": "bluesky:quote:abcde",
                "source": "bluesky",
                "actor_id": "bluesky:dave.bsky.social",
                "actor_name": "@dave.bsky.social",
                "target_id": "bluesky:alice.bsky.social",
                "target_name": "@alice.bsky.social",
                "event_type": "quote",
                "timestamp": "2026-11-10T08:10:00Z",
                "confidence": 1.0,
                "meta": {"cid": "bafyrei..."},
            },
        ]

        required_keys = {
            "id", "source", "actor_id", "actor_name", "target_id", "target_name",
            "event_type", "timestamp", "confidence", "meta"
        }

        for ev in events:
            self.assertTrue(required_keys.issubset(ev.keys()))
            self.assertIn(ev["source"], ["threads", "x", "bluesky", "mastodon"])
            self.assertIn(ev["event_type"], ["follow", "reply", "quote", "repost", "like", "mention", "interaction"])

    def test_identity_resolution_dedup(self):
        """驗證跨社群同質帳號對齊推導 (Cross-Platform Identity Resolution)。"""
        # 模擬跨平台帳號對齊表 (例如 Alice 在不同社群的 handle 綁定到同一實體 entity:alice)
        identity_bindings = {
            "threads:alice": "entity:alice",
            "x:alice_tw": "entity:alice",
            "bluesky:alice.bsky.social": "entity:alice",
            "threads:bob": "entity:bob",
            "x:bob_official": "entity:bob",
        }

        raw_events = [
            {"source": "threads", "actor_id": "threads:alice", "target_id": "threads:bob", "event_type": "reply"},
            {"source": "x", "actor_id": "x:alice_tw", "target_id": "x:bob_official", "event_type": "mention"},
            {"source": "bluesky", "actor_id": "bluesky:alice.bsky.social", "target_id": "bluesky:unknown_user", "event_type": "quote"},
        ]

        # 投影至統一實體宇宙 (Unified Entity Space)
        unified_events = []
        for e in raw_events:
            unified_actor = identity_bindings.get(e["actor_id"], e["actor_id"])
            unified_target = identity_bindings.get(e["target_id"], e["target_id"])
            unified_events.append({
                "actor": unified_actor,
                "target": unified_target,
                "type": e["event_type"],
            })

        # Alice ➔ Bob 在 Threads 與 X 上的跨平台互動被成功彙整為同一組關係
        alice_to_bob = [e for e in unified_events if e["actor"] == "entity:alice" and e["target"] == "entity:bob"]
        self.assertEqual(len(alice_to_bob), 2)
        self.assertEqual({e["type"] for e in alice_to_bob}, {"reply", "mention"})


if __name__ == "__main__":
    unittest.main()

