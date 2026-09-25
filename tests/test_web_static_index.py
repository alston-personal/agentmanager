import json

import pytest

from capabilities.web_static_index import render_static_index, render_to_file


def spec(**overrides):
    value = {
        "schema": "agentos.web-static-index/v1",
        "title": "宅向分析結果",
        "heading": "坐北朝南",
        "summary": "文昌位在東南方；這是可分享的公開摘要。",
        "canonical_url": "https://studio.milkcat.org/fengshui/result/demo",
        "lang": "zh-Hant",
        "facts": [{"label": "文昌位", "value": "東南方"}],
        "sections": [{"heading": "摘要", "text": "完整互動仍由動態應用提供。"}],
        "links": [{"label": "開啟互動工具", "url": "https://studio.milkcat.org/fengshui/"}],
    }
    value.update(overrides)
    return value


def test_renders_primary_content_without_javascript():
    body = render_static_index(spec())
    assert "<h1>坐北朝南</h1>" in body
    assert "文昌位在東南方" in body
    assert '<link rel="canonical" href="https://studio.milkcat.org/fengshui/result/demo">' in body
    assert '<meta name="robots" content="index,follow">' in body
    assert "<script" not in body


def test_noindex_is_explicit_and_arbitrary_html_is_escaped():
    body = render_static_index(spec(robots="noindex,nofollow", summary="<b>secret-ish</b>"))
    assert '<meta name="robots" content="noindex,nofollow">' in body
    assert "&lt;b&gt;secret-ish&lt;/b&gt;" in body
    assert "<b>secret-ish</b>" not in body


def test_structured_data_is_optional_machine_readable_json():
    body = render_static_index(spec(structured_data={"@context": "https://schema.org", "@type": "WebPage"}))
    assert 'application/ld+json' in body
    assert '"@type":"WebPage"' in body


def test_render_receipt(tmp_path):
    output = tmp_path / "index.html"
    receipt = render_to_file(spec(), output)
    assert output.exists()
    assert receipt["schema"] == "agentos.web-static-index-receipt/v1"
    assert receipt["capability_id"] == "web.static-index.render"
    assert len(receipt["sha256"]) == 64


def test_rejects_non_http_canonical():
    with pytest.raises(ValueError):
        render_static_index(spec(canonical_url="javascript:alert(1)"))
