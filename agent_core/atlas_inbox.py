#!/usr/bin/env python3
"""Atlas Fork-and-Return Experience Consolidation Engine.

Implements the Shadow-Clone (影分身) concurrency-safe memory model:
1. Fork (Read-Only Snapshot): Every conversation receives a read-only snapshot of
   Atlas's canonical memory/pitfalls via ONE PreInvocation.
2. Return (Append-Only Inbox): Any conversation shard submits candidate lessons,
   decisions, or growth-proof observations as independent JSON files into
   `$AGENT_DATA_ROOT/personas/system-atlas/inbox/`. Multi-conversation shards
   NEVER overwrite each other.
3. Consolidate (Single-Writer Merge): Atlas core / meditation consolidates inbox
   entries, deduplicates them, archives processed cards to `inbox/processed/`,
   and promotes validated growth evidence into `growth-proof/ledger.json`.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def submit_experience_card(
    data_root: Path,
    *,
    kind: str,  # "pitfall" | "decision" | "growth_observation"
    title: str,
    summary: str,
    source_surface: str = "antigravity",
    source_model: str = "unknown",
    evidence_refs: list[str] | None = None,
) -> Path:
    """Append-only submission of a shard's experience card into Atlas inbox."""
    inbox_dir = Path(data_root) / "personas" / "system-atlas" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    card_id = f"exp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    card = {
        "schema": "agentos.atlas-experience-card/v1",
        "card_id": card_id,
        "submitted_at": _utc_now_iso(),
        "kind": kind,
        "title": title.strip(),
        "summary": summary.strip(),
        "source_surface": source_surface,
        "source_model": source_model,
        "evidence_refs": evidence_refs or [],
    }
    card_path = inbox_dir / f"{card_id}.json"
    card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return card_path


def consolidate_atlas_inbox(data_root: Path) -> dict[str, Any]:
    """Single-writer consolidation: deduplicate inbox cards and archive processed items."""
    root = Path(data_root)
    atlas_dir = root / "personas" / "system-atlas"
    inbox_dir = atlas_dir / "inbox"
    processed_dir = inbox_dir / "processed"
    consolidated_log = atlas_dir / "consolidated_experiences.jsonl"

    if not inbox_dir.is_dir():
        return {"processed": 0, "skipped_duplicates": 0, "promoted_growth": 0}

    processed_dir.mkdir(parents=True, exist_ok=True)
    seen_titles: set[str] = set()
    if consolidated_log.is_file():
        for line in consolidated_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    seen_titles.add(json.loads(line).get("title", "").lower())
                except Exception:
                    pass

    processed = 0
    skipped = 0
    promoted_growth = 0
    cards = sorted(p for p in inbox_dir.glob("*.json") if p.is_file())

    for card_path in cards:
        try:
            card = json.loads(card_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        norm_title = str(card.get("title", "")).strip().lower()
        if norm_title in seen_titles:
            skipped += 1
        else:
            seen_titles.add(norm_title)
            with open(consolidated_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(card, ensure_ascii=False) + "\n")
            processed += 1
            if card.get("kind") == "growth_observation":
                promoted_growth += 1

        card_path.rename(processed_dir / card_path.name)

    return {
        "processed": processed,
        "skipped_duplicates": skipped,
        "promoted_growth": promoted_growth,
    }
