"""Human-corrected OCR memory.

This capability stores confirmed OCR corrections scoped by document context and
returns either a conservative auto-correction or a suggestion. It never retrains
the OCR engine and never promotes a global rule from a single human correction.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def normalize_observed(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper()


@dataclass(frozen=True)
class OCRMemoryContext:
    template_id: str = ""
    stamp_id: str = ""
    entity_id: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "OCRMemoryContext":
        value = value or {}
        return cls(
            template_id=str(value.get("template_id") or ""),
            stamp_id=str(value.get("stamp_id") or ""),
            entity_id=str(value.get("entity_id") or ""),
        )


@dataclass(frozen=True)
class OCRMemoryDecision:
    decision: str
    corrected_value: Any = None
    score: float = 0.0
    confirmed_count: int = 0
    reason: str = ""


class OCRMemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS ocr_corrections(
              id TEXT PRIMARY KEY,
              field_name TEXT NOT NULL,
              observed_value TEXT NOT NULL,
              corrected_value_json TEXT NOT NULL,
              template_id TEXT NOT NULL DEFAULT '',
              stamp_id TEXT NOT NULL DEFAULT '',
              entity_id TEXT NOT NULL DEFAULT '',
              confirmed_count INTEGER NOT NULL DEFAULT 1,
              last_actor TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(field_name,observed_value,corrected_value_json,template_id,stamp_id,entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ocr_correction_lookup
              ON ocr_corrections(field_name,observed_value,template_id,stamp_id,entity_id);
            """)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def remember(
        self,
        *,
        field_name: str,
        observed_value: Any,
        corrected_value: Any,
        context: OCRMemoryContext,
        actor: str | None = None,
    ) -> None:
        observed = normalize_observed(observed_value)
        corrected_json = json.dumps(corrected_value, ensure_ascii=False, sort_keys=True)
        if not observed or normalize_observed(corrected_value) == observed:
            return
        with self.connect() as db:
            existing = db.execute(
                """SELECT id,confirmed_count FROM ocr_corrections
                   WHERE field_name=? AND observed_value=? AND corrected_value_json=?
                     AND template_id=? AND stamp_id=? AND entity_id=?""",
                (
                    field_name, observed, corrected_json,
                    context.template_id, context.stamp_id, context.entity_id,
                ),
            ).fetchone()
            if existing:
                db.execute(
                    """UPDATE ocr_corrections
                       SET confirmed_count=confirmed_count+1,last_actor=?,updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (actor, existing["id"]),
                )
            else:
                db.execute(
                    """INSERT INTO ocr_corrections(
                         id,field_name,observed_value,corrected_value_json,
                         template_id,stamp_id,entity_id,confirmed_count,last_actor
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()), field_name, observed, corrected_json,
                        context.template_id, context.stamp_id, context.entity_id, 1, actor,
                    ),
                )

    def resolve(
        self,
        *,
        field_name: str,
        observed_value: Any,
        context: OCRMemoryContext,
    ) -> OCRMemoryDecision:
        observed = normalize_observed(observed_value)
        if not observed:
            return OCRMemoryDecision("none", reason="missing_observed_value")
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM ocr_corrections
                   WHERE field_name=? AND observed_value=?
                   ORDER BY confirmed_count DESC, updated_at DESC""",
                (field_name, observed),
            ).fetchall()
        if not rows:
            return OCRMemoryDecision("none", reason="no_matching_correction")

        best: tuple[float, sqlite3.Row, str] | None = None
        for row in rows:
            count = int(row["confirmed_count"])
            score = 0.0
            reason = ""
            if context.stamp_id and row["stamp_id"] and context.stamp_id == row["stamp_id"]:
                score, reason = 0.99, "same_stamp_exact_observation"
            elif (
                context.entity_id and row["entity_id"] and context.entity_id == row["entity_id"]
                and context.template_id and row["template_id"] == context.template_id
            ):
                score, reason = (0.96 if count >= 2 else 0.86), "same_entity_template"
            elif context.template_id and row["template_id"] == context.template_id:
                score, reason = min(0.84, 0.70 + 0.03 * min(count, 4)), "same_template"
            if score and (best is None or score > best[0]):
                best = (score, row, reason)

        if best is None:
            return OCRMemoryDecision("none", reason="context_not_close_enough")
        score, row, reason = best
        corrected = json.loads(row["corrected_value_json"])
        count = int(row["confirmed_count"])
        auto = (
            reason == "same_stamp_exact_observation"
            or (reason == "same_entity_template" and count >= 2)
        )
        return OCRMemoryDecision(
            "auto_correct" if auto else "suggest",
            corrected_value=corrected,
            score=score,
            confirmed_count=count,
            reason=reason,
        )


def context_from_extraction(raw: Mapping[str, Any], fields: Mapping[str, Any]) -> OCRMemoryContext:
    template = raw.get("template") or {}
    stamp = raw.get("stamp_recognition") or {}
    template_id = str(template.get("document_type") or "")
    stamp_id = str(stamp.get("stamp_id") or "")
    entity_id = str(stamp.get("entity_id") or fields.get("seller_tax_id") or "")
    return OCRMemoryContext(template_id=template_id, stamp_id=stamp_id, entity_id=entity_id)
