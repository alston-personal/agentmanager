import json
from pathlib import Path
import pytest
from scripts.threads_intel_crawler import (
    get_mio_interests,
    run_crawler,
)
import scripts.threads_intel_crawler as crawler_mod
import scripts.mio_intel_hub as hub_mod


def test_get_mio_interests():
    interests = get_mio_interests()
    assert isinstance(interests, list)
    assert len(interests) > 0
    assert any("貓" in x or "散步" in x or "咖啡" in x for x in interests)


def test_run_crawler_with_mock_discovery(tmp_path, monkeypatch):
    test_file = tmp_path / "intel_candidates.json"
    monkeypatch.setattr(hub_mod, "CANDIDATES_FILE", test_file)
    monkeypatch.setattr(hub_mod, "BASE_DATA_DIR", tmp_path)
    monkeypatch.setattr(crawler_mod, "BASE_DATA_DIR", tmp_path)
    monkeypatch.setattr(crawler_mod, "PENDING_QUEUE", tmp_path / "pending.json")

    mock_candidates = [
        {
            "url": "https://www.threads.net/@coffee_lover/post/ABC123xyz",
            "username": "coffee_lover",
            "shortcode": "ABC123xyz",
            "media_id": "1234567890123456",
            "matched_topic": "手沖咖啡",
        }
    ]

    monkeypatch.setattr(
        crawler_mod,
        "discover_threads_candidates",
        lambda topic, max_results=3: mock_candidates if topic == "手沖咖啡" else [],
    )
    monkeypatch.setattr(
        crawler_mod,
        "fetch_threads_preview",
        lambda url, code, user: {"author": "@coffee_lover", "title": "咖啡沖煮技巧", "text": "今天用V60沖了一杯耶加雪菲..."},
    )
    monkeypatch.setattr(
        crawler_mod,
        "get_mio_interests",
        lambda: ["手沖咖啡", "貓咪觀察"],
    )

    res = run_crawler(max_new_candidates=2)
    assert res["ok"] is True
    assert res["new_candidates_added"] == 1
    assert res["total_candidates"] == 1
    assert res["added"][0]["id"] == "1234567890123456"
    candidate = json.loads(test_file.read_text(encoding="utf-8"))["candidates"][0]
    assert candidate["id_provenance"] == "shortcode_derived_unverified"
    assert candidate["reply_allowed"] is False

    # Verify deduplication on second run
    res2 = run_crawler(max_new_candidates=2)
    assert res2["ok"] is True
    assert res2["new_candidates_added"] == 0
    assert res2["total_candidates"] == 1

