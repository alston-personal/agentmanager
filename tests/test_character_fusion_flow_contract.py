from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_flow_prompt_is_committed_before_generate() -> None:
    text = (ROOT / "scripts" / "character_fusion_worker.py").read_text(encoding="utf-8")
    typed = text.index('flow_prompt_not_typed')
    commit = text.index('flow_prompt_commit_button_unavailable')
    generate = text.index('flow_generate_button_unavailable')
    assert typed < commit < generate
    assert '/^(done|完成|套用|儲存)$/i' in text
