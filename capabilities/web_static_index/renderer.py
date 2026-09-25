from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from string import Template
from typing import Any
from urllib.parse import urlparse


CAPABILITY_ID = "web.static-index.render"
SPEC_SCHEMA = "agentos.web-static-index/v1"
RECEIPT_SCHEMA = "agentos.web-static-index-receipt/v1"
_TEMPLATE = Path(__file__).with_name("templates") / "index.html"
_ALLOWED_ROBOTS = {"index,follow", "index,nofollow", "noindex,follow", "noindex,nofollow"}


def _text(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _attr(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _http_url(value: Any, field: str) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute http(s) URL")
    return raw


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"schema must be {SPEC_SCHEMA}")

    out = dict(spec)
    for field in ("title", "heading", "summary", "canonical_url"):
        if not str(out.get(field) or "").strip():
            raise ValueError(f"{field} is required")

    out["canonical_url"] = _http_url(out["canonical_url"], "canonical_url")
    out["lang"] = str(out.get("lang") or "zh-Hant").strip()
    out["robots"] = str(out.get("robots") or "index,follow").replace(" ", "").lower()
    if out["robots"] not in _ALLOWED_ROBOTS:
        raise ValueError(f"unsupported robots directive: {out['robots']}")

    if out.get("og_image"):
        out["og_image"] = _http_url(out["og_image"], "og_image")

    for collection in ("facts", "sections", "links"):
        value = out.get(collection) or []
        if not isinstance(value, list):
            raise ValueError(f"{collection} must be a list")
        if any(not isinstance(item, dict) for item in value):
            raise ValueError(f"{collection} entries must be objects")

    if out.get("structured_data") is not None and not isinstance(out["structured_data"], dict):
        raise ValueError("structured_data must be an object")
    return out


def _render_facts(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        label = _text(item.get("label"))
        value = _text(item.get("value"))
        if not label or not value:
            continue
        rows.append(f"      <dt>{label}</dt>\n      <dd>{value}</dd>")
    if not rows:
        return ""
    return "    <dl>\n" + "\n".join(rows) + "\n    </dl>"


def _render_sections(items: list[dict[str, Any]]) -> str:
    chunks = []
    for item in items:
        heading = _text(item.get("heading"))
        body = _text(item.get("text"))
        if not heading or not body:
            continue
        chunks.append(
            "    <section>\n"
            f"      <h2>{heading}</h2>\n"
            f"      <p>{body}</p>\n"
            "    </section>"
        )
    return "\n".join(chunks)


def _render_links(items: list[dict[str, Any]]) -> str:
    links = []
    for item in items:
        label = _text(item.get("label"))
        raw_url = str(item.get("url") or "").strip()
        if not label or not raw_url:
            continue
        url = _attr(_http_url(raw_url, "links[].url"))
        links.append(f'      <li><a href="{url}">{label}</a></li>')
    if not links:
        return ""
    return "    <nav aria-label=\"Related links\">\n      <ul>\n" + "\n".join(links) + "\n      </ul>\n    </nav>"


def render_static_index(spec: dict[str, Any]) -> str:
    value = validate_spec(spec)
    template = Template(_TEMPLATE.read_text(encoding="utf-8"))

    og_optional = []
    if value.get("site_name"):
        og_optional.append(f'  <meta property="og:site_name" content="{_attr(value["site_name"])}">')
    if value.get("og_image"):
        og_optional.append(f'  <meta property="og:image" content="{_attr(value["og_image"])}">')

    structured_data = ""
    if value.get("structured_data"):
        payload = json.dumps(value["structured_data"], ensure_ascii=False, separators=(",", ":"))
        payload = payload.replace("</", "<\\/")
        structured_data = f'  <script type="application/ld+json">{payload}</script>'

    return template.substitute(
        lang=_attr(value["lang"]),
        title=_text(value["title"]),
        summary_attr=_attr(value["summary"]),
        robots=_attr(value["robots"]),
        canonical_url=_attr(value["canonical_url"]),
        og_title=_attr(value.get("og_title") or value["title"]),
        og_description=_attr(value.get("og_description") or value["summary"]),
        og_optional="\n".join(og_optional),
        twitter_card="summary_large_image" if value.get("og_image") else "summary",
        structured_data=structured_data,
        heading=_text(value["heading"]),
        summary=_text(value["summary"]),
        facts=_render_facts(value["facts"]),
        sections=_render_sections(value["sections"]),
        links=_render_links(value["links"]),
    )


def render_to_file(spec: dict[str, Any], output: str | Path) -> dict[str, Any]:
    body = render_static_index(spec)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "schema": RECEIPT_SCHEMA,
        "capability_id": CAPABILITY_ID,
        "output": str(target),
        "sha256": digest,
        "bytes": len(body.encode("utf-8")),
        "robots": validate_spec(spec)["robots"],
        "canonical_url": validate_spec(spec)["canonical_url"],
    }
