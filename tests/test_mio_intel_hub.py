import json
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path
import pytest
from scripts.mio_intel_hub import (
    shortcode_to_media_id,
    media_id_to_shortcode,
    parse_and_validate_url,
    MioIntelHandler,
)
import scripts.mio_intel_hub as hub_mod


def test_shortcode_math_bijective():
    shortcodes = ["C9d_W12SZlX", "Dda08MBFKJa", "DfYhza2GSsc", "A", "z", "ZZZ"]
    for code in shortcodes:
        mid = shortcode_to_media_id(code)
        assert mid.isdigit()
        rev = media_id_to_shortcode(mid)
        assert rev == code


def test_parse_and_validate_url():
    # Regular post
    u1 = "https://www.threads.net/@mio.milkcat/post/Dda08MBFKJa"
    info1 = parse_and_validate_url(u1)
    assert info1["username"] == "mio.milkcat"
    assert info1["shortcode"] == "Dda08MBFKJa"
    assert info1["media_id"] == "3988733254480208474"

    # threads.com variant
    u2 = "https://threads.com/@user.name/post/C9d_W12SZlX"
    info2 = parse_and_validate_url(u2)
    assert info2["username"] == "user.name"
    assert info2["shortcode"] == "C9d_W12SZlX"

    # /t/ short format
    u3 = "https://www.threads.net/t/C9d_W12SZlX"
    info3 = parse_and_validate_url(u3)
    assert info3["username"] == ""
    assert info3["shortcode"] == "C9d_W12SZlX"

    # Invalid URL
    with pytest.raises(ValueError, match="請輸入有效的 Threads 貼文連結"):
        parse_and_validate_url("https://facebook.com/post/123")


def test_share_url_is_read_only_discovery_and_spoofed_host_is_rejected():
    candidate = parse_and_validate_url("https://www.threads.com/share/GdMiITUe6/")
    assert candidate["media_id"] == "share:GdMiITUe6"
    assert candidate["id_provenance"] == "share_url_unresolved"
    assert candidate["canonical_url"] == "https://www.threads.com/share/GdMiITUe6/"
    import pytest
    for invalid in (
        "https://evil.example/https://www.threads.com/@x/post/AbCd",
        "https://www.threads.com.evil.example/@x/post/AbCd",
        "https://www.threads.com/@x/post/AbCd?redirect=evil",
        "https://www.threads.com/share/GdMiITUe6/../../../other",
        "http://www.threads.com/@x/post/AbCd",
    ):
        with pytest.raises(ValueError):
            parse_and_validate_url(invalid)


def test_http_api_endpoints(tmp_path, monkeypatch):
    test_file = tmp_path / "intel_candidates.json"
    monkeypatch.setattr(hub_mod, "CANDIDATES_FILE", test_file)
    monkeypatch.setattr(hub_mod, "BASE_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        hub_mod,
        "fetch_threads_preview",
        lambda url, code, user: {"author": f"@{user}", "title": "Test Title", "text": "Post snippet"},
    )

    server = HTTPServer(("127.0.0.1", 0), MioIntelHandler)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    base = f"http://127.0.0.1:{port}"

    try:
        # 1. Healthz
        with urllib.request.urlopen(f"{base}/healthz") as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["ok"] is True
            assert data["service"] == "mio-intel-hub"

        # 2. GET empty feed
        with urllib.request.urlopen(f"{base}/api/feed") as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["summary"]["total"] == 0
            assert len(data["candidates"]) == 0

        # 3. POST new feed
        req = urllib.request.Request(
            f"{base}/api/feed",
            data=json.dumps({
                "url": "https://www.threads.net/@mio.milkcat/post/Dda08MBFKJa",
                "note": "測試投遞給澪",
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as res:
            assert res.status == 201
            data = json.loads(res.read().decode())
            assert data["ok"] is True
            assert data["already_submitted"] is False
            assert data["candidate"]["id"] == "3988733254480208474"
            assert data["candidate"]["id_provenance"] == "shortcode_derived_unverified"
            assert data["candidate"]["reply_allowed"] is False
            assert data["candidate"]["user_note"] == "測試投遞給澪"

        # 4. POST duplicate feed
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["ok"] is True
            assert data["already_submitted"] is True

        # 5. GET feed with candidate
        with urllib.request.urlopen(f"{base}/api/feed") as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            assert data["summary"]["total"] == 1
            assert data["summary"]["pending_review"] == 1
            assert len(data["candidates"]) == 1
            assert data["candidates"][0]["id"] == "3988733254480208474"

    finally:
        server.shutdown()
        server.server_close()

