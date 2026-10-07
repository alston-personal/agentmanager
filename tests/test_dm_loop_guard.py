import unittest

from agentos_node.social.dm_loop_guard import (
    message_fingerprint,
    record_auto_reply,
    record_consumed,
    reset_hop_budget,
    should_auto_reply,
)


def inbound(mid="m1", text="hello", sender="mio.milkcat"):
    return {
        "direction":"inbound",
        "message_id":mid,
        "text":text,
        "actor_username":sender,
    }


class DMLoopGuardTests(unittest.TestCase):
    def test_allows_first_expected_inbound(self):
        d=should_auto_reply(
            event=inbound(),
            state={},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertTrue(d.allow)
        self.assertEqual(d.reason,"allow")

    def test_blocks_own_outbound_and_unexpected_peer(self):
        own=should_auto_reply(
            event={"direction":"outbound","message_id":"x","text":"x","actor_username":"oursong_alstonhuang"},
            state={},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(own.reason,"not_inbound")

        other=should_auto_reply(
            event=inbound(sender="someone_else"),
            state={},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(other.reason,"unexpected_peer")

    def test_blocks_duplicate_id_and_semantic_duplicate(self):
        fp=message_fingerprint(sender="mio.milkcat",text="same text")
        by_id=should_auto_reply(
            event=inbound(mid="m1",text="new"),
            state={"processed_message_ids":["m1"]},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(by_id.reason,"duplicate_message_id")

        semantic=should_auto_reply(
            event=inbound(mid="m2",text="  SAME   TEXT "),
            state={"processed_fingerprints":[fp]},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(semantic.reason,"semantic_duplicate")

    def test_blocks_cooldown_and_hop_budget(self):
        cooldown=should_auto_reply(
            event=inbound(),
            state={"last_auto_reply_epoch":950},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(cooldown.reason,"cooldown")

        hops=should_auto_reply(
            event=inbound(mid="m2"),
            state={"auto_hops":2},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            now_epoch=1000,
        )
        self.assertEqual(hops.reason,"hop_budget_exhausted")

    def test_record_and_reset_state(self):
        event=inbound()
        fp=message_fingerprint(sender="mio.milkcat",text="hello")
        s=record_auto_reply(event=event,state={},fingerprint=fp,now_epoch=1000)
        self.assertEqual(s["auto_hops"],1)
        self.assertEqual(s["processed_message_ids"],["m1"])
        self.assertEqual(s["processed_fingerprints"],[fp])
        self.assertEqual(reset_hop_budget(s)["auto_hops"],0)

    def test_consumed_event_is_never_replied_later_after_cooldown(self):
        event=inbound(mid="m9",text="cooldown message")
        fp=message_fingerprint(sender="mio.milkcat",text="cooldown message")
        state=record_consumed(event=event,state={"last_auto_reply_epoch":950},fingerprint=fp)
        later=should_auto_reply(
            event=event,
            state=state,
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            hop_window_seconds=600,
            now_epoch=2000,
        )
        self.assertFalse(later.allow)
        self.assertEqual(later.reason,"duplicate_message_id")

    def test_hop_budget_resets_after_quiet_window(self):
        d=should_auto_reply(
            event=inbound(mid="m10",text="new burst"),
            state={"auto_hops":2,"last_auto_reply_epoch":1000},
            own_account="oursong_alstonhuang",
            peer_account="mio.milkcat",
            max_auto_hops=2,
            cooldown_seconds=120,
            hop_window_seconds=600,
            now_epoch=1701,
        )
        self.assertTrue(d.allow)


if __name__=="__main__":
    unittest.main()
