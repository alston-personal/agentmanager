import json
import re
from pathlib import Path
import pytest
from scripts import mio_persona_social_loop_user as mio

CLICHE_OPENER_REGEX = re.compile(
    r"^(確實[，,]|對呀[，,]\s*(確實|能|看到)|看到你(?:分享|說)的|你說的沒錯)",
    re.IGNORECASE,
)

PREACHY_CLOSING_REGEX = re.compile(
    r"(才能(?:更完整|真正)|體感最誠實|生活就是如此|保護原生種確實很重要|這才是真正的)",
    re.IGNORECASE,
)


def test_cliche_detector():
    # Bad AI samples from historical logs
    bad_samples = [
        "確實是，遊蕩貓對野生動物和生態的影響真的蠻需要關注的。謝謝你的提醒，保護原生種確實很重要 🌿",
        "對呀，能同時考慮對動物的喜愛與生態的影響，才是更完整的關心 🌿",
        "看到你分享的照片，真的很讓人放鬆 😆",
    ]
    for text in bad_samples:
        has_cliche = bool(CLICHE_OPENER_REGEX.search(text) or PREACHY_CLOSING_REGEX.search(text))
        assert has_cliche, f"Expected cliché to be caught: {text}"

    # Good natural samples
    good_samples = [
        "笑死我上次也是這樣，直接在路邊愣住 XDD",
        "這大名很有氣勢，但喊完之前，貓可能已經走了。平常會叫牠什麼小名？",
        "風先讓厚針織入選，太陽再來推翻決定。這兩位很難合作。",
        "原來是穿搭版的北風與太陽，太陽這次也贏了，袖子都捲起來了。",
    ]
    for text in good_samples:
        assert not CLICHE_OPENER_REGEX.search(text), f"False positive opener: {text}"
        assert not PREACHY_CLOSING_REGEX.search(text), f"False positive closing: {text}"


def test_reply_policy_contains_anti_ai_directives():
    policy_path = Path("/home/ubuntu/agent-data/personas/sunlake-milkcat/reply_policy.json")
    assert policy_path.is_file()
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    directives = data.get("conversation_integrity", {}).get("anti_ai_cliche_directives", {})
    assert "ban_echoing_openers" in directives
    assert "ban_preachy_closings" in directives
    assert "ban_formulaic_emojis" in directives
    assert "natural_cadence" in directives

