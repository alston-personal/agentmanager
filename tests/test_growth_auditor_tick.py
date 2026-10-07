from pathlib import Path

from scripts.growth_auditor_tick import _read_new_jsonl


def test_read_new_jsonl_uses_cursor(tmp_path: Path):
    inbox = tmp_path / "inbox.jsonl"
    cursor = tmp_path / "inbox.cursor"
    inbox.write_text('{"source_experience":["a"]}\n', encoding="utf-8")

    first, offset = _read_new_jsonl(inbox, cursor)
    assert len(first) == 1

    cursor.write_text(str(offset) + "\n", encoding="utf-8")
    inbox.write_text(
        inbox.read_text(encoding="utf-8") + '{"source_experience":["b"]}\n',
        encoding="utf-8",
    )

    second, new_offset = _read_new_jsonl(inbox, cursor)
    assert len(second) == 1
    assert second[0]["source_experience"] == ["b"]
    assert new_offset > offset
