from agentos_node.social.dm_loop_guard import (
    message_fingerprint,
    record_auto_reply,
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


def test_allows_first_expected_inbound():
    d=should_auto_reply(
        event=inbound(),
        state={},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert d.allow is True
    assert d.reason=="allow"


def test_blocks_own_outbound_and_unexpected_peer():
    own=should_auto_reply(
        event={"direction":"outbound","message_id":"x","text":"x","actor_username":"oursong_alstonhuang"},
        state={},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert own.reason=="not_inbound"

    other=should_auto_reply(
        event=inbound(sender="someone_else"),
        state={},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert other.reason=="unexpected_peer"


def test_blocks_duplicate_id_and_semantic_duplicate():
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
    assert by_id.reason=="duplicate_message_id"

    semantic=should_auto_reply(
        event=inbound(mid="m2",text="  SAME   TEXT "),
        state={"processed_fingerprints":[fp]},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert semantic.reason=="semantic_duplicate"


def test_blocks_cooldown_and_hop_budget():
    cooldown=should_auto_reply(
        event=inbound(),
        state={"last_auto_reply_epoch":950},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert cooldown.reason=="cooldown"

    hops=should_auto_reply(
        event=inbound(mid="m2"),
        state={"auto_hops":2},
        own_account="oursong_alstonhuang",
        peer_account="mio.milkcat",
        max_auto_hops=2,
        cooldown_seconds=120,
        now_epoch=1000,
    )
    assert hops.reason=="hop_budget_exhausted"


def test_record_and_reset_state():
    event=inbound()
    fp=message_fingerprint(sender="mio.milkcat",text="hello")
    s=record_auto_reply(event=event,state={},fingerprint=fp,now_epoch=1000)
    assert s["auto_hops"]==1
    assert s["processed_message_ids"]==["m1"]
    assert s["processed_fingerprints"]==[fp]
    assert reset_hop_budget(s)["auto_hops"]==0
