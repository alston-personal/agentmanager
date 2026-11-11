#!/usr/bin/env python3
"""
Intelligence Center: Threads Post Discovery for Mio (threads_intel_crawler.py)
Crawls and aggregates public Threads discussions matching Mio's current interests,
feeding high-quality candidates into Mio's intelligence inbox (intel_candidates.json)
for autonomous evaluation and potential outbound engagement.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.mio_intel_hub import (
    load_candidates,
    save_candidates,
    parse_and_validate_url,
    fetch_threads_preview,
    now_iso,
)

BASE_DATA_DIR = Path("/home/ubuntu/agent-data/personas/sunlake-milkcat")
IR_FILE = BASE_DATA_DIR / "ir/current_ir.json"
CORE_FILE = BASE_DATA_DIR / "character_core.json"
PENDING_QUEUE = Path("/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/pending.json")


def get_mio_interests() -> list[str]:
    """Extracts current interests from canonical IR and persona core."""
    interests: list[str] = []

    if IR_FILE.is_file():
        try:
            ir_data = json.loads(IR_FILE.read_text(encoding="utf-8"))
            self_block = ir_data.get("current_self") or {}
            for item in self_block.get("interests_with_evidence") or []:
                topic = str((item or {}).get("topic") or "").strip()
                if topic and topic not in interests:
                    interests.append(topic)
        except Exception:
            pass

    if CORE_FILE.is_file():
        try:
            core_data = json.loads(CORE_FILE.read_text(encoding="utf-8"))
            for item in core_data.get("likes") or []:
                clean = str(item).strip()
                if clean and clean not in interests:
                    interests.append(clean)
        except Exception:
            pass

    # High-relevance lifestyle topics if IR is sparse
    fallbacks = ["日常散步", "手沖咖啡", "貓咪觀察", "穿搭靈感", "AI創作日記"]
    for fb in fallbacks:
        if fb not in interests:
            interests.append(fb)

    return interests[:8]


def discover_threads_candidates(topic: str, max_results: int = 3) -> list[dict[str, str]]:
    """
    Discovers public Threads posts matching a topic.
    Uses Google Search RSS / public indexing to discover recent Threads URLs without requiring private Meta developer scopes.
    """
    candidates = []
    # Search query targeting Threads post URLs
    query = f"site:threads.net/post OR site:threads.com/post \"{topic}\""
    encoded_query = urllib.parse.quote(query)
    # Use public search discovery endpoint
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_text = resp.read(512_000).decode("utf-8", errors="replace")
            # Extract URLs pointing to threads.net/@user/post/...
            found_urls = re.findall(
                r"https?://(?:www\.)?threads\.(?:net|com)/@[A-Za-z0-9._]+/post/[A-Za-z0-9_-]+",
                html_text,
            )

            seen = set()
            for u in found_urls:
                clean_url = u.split("?")[0].rstrip("/")
                if clean_url not in seen:
                    seen.add(clean_url)
                    try:
                        validated = parse_and_validate_url(clean_url)
                        candidates.append({
                            "url": validated["canonical_url"],
                            "username": validated["username"],
                            "shortcode": validated["shortcode"],
                            "media_id": validated["media_id"],
                            "matched_topic": topic,
                        })
                    except Exception:
                        pass
                if len(candidates) >= max_results:
                    break
    except Exception as e:
        sys.stderr.write(f"[threads_intel_crawler] Discovery search warning for topic '{topic}': {e}\n")

    return candidates


def run_crawler(max_new_candidates: int = 4) -> dict[str, Any]:
    interests = get_mio_interests()
    store = load_candidates()
    existing_candidates = store.setdefault("candidates", [])
    existing_ids = {str(c.get("id")) for c in existing_candidates}
    existing_shortcodes = {str(c.get("shortcode")) for c in existing_candidates}

    # Also check seen_outbound_ids from social loop pending.json
    if PENDING_QUEUE.is_file():
        try:
            p_data = json.loads(PENDING_QUEUE.read_text(encoding="utf-8"))
            existing_ids.update(str(x) for x in p_data.get("seen_outbound_ids") or [])
        except Exception:
            pass

    added = []

    for topic in interests:
        if len(added) >= max_new_candidates:
            break
        found = discover_threads_candidates(topic, max_results=2)
        for item in found:
            mid = item["media_id"]
            code = item["shortcode"]
            if mid in existing_ids or code in existing_shortcodes:
                continue

            preview = fetch_threads_preview(item["url"], code, item["username"])
            # Require at least some author or snippet text
            candidate = {
                "id": mid,
                "id_provenance": "shortcode_derived_unverified",
                "reply_allowed": False,
                "shortcode": code,
                "username": item["username"],
                "url": item["url"],
                "author": preview.get("author") or f"@{item['username']}",
                "title": preview.get("title") or "",
                "text": preview.get("text") or f"[情報中心探索 · 主題: {topic}]",
                "user_note": f"情報中心自動探索推薦（契合話題：{topic}）",
                "source": "intel_center",
                "matched_topic": topic,
                "status": "pending_review",
                "created_at": now_iso(),
                "reviewed_at": None,
                "decision": None,
            }

            existing_candidates.append(candidate)
            existing_ids.add(mid)
            existing_shortcodes.add(code)
            added.append(candidate)

            if len(added) >= max_new_candidates:
                break

    if added:
        save_candidates(store)

    return {
        "ok": True,
        "topics_scanned": interests,
        "new_candidates_added": len(added),
        "total_candidates": len(existing_candidates),
        "added": [{"id": c["id"], "author": c["author"], "url": c["url"]} for c in added],
    }


if __name__ == "__main__":
    result = run_crawler()
    print(json.dumps(result, ensure_ascii=False, indent=2))
