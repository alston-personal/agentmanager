#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from rapidocr import RapidOCR
from services.invoice_intake.template_ocr import (
    extract_template_invoice,
    ocr_page_evidence,
)

FIELDS = (
    "invoice_number",
    "invoice_date",
    "buyer_tax_id",
    "seller_tax_id",
    "amount_before_tax",
    "tax_amount",
    "total_amount",
)
MONEY_FIELDS = {"amount_before_tax", "tax_amount", "total_amount"}


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _compact(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                cur[-1] + 1,
                prev[j] + 1,
                prev[j - 1] + (ca != cb),
            ))
        prev = cur
    return prev[-1]


def _expected_forms(field: str, expected: Any) -> list[str]:
    if field == "invoice_number":
        return [_compact(expected)]
    if field == "invoice_date":
        y, m, d = map(int, str(expected).split("-"))
        roc = y - 1911
        return [
            f"{roc}{m}{d}",
            f"{roc:03d}{m:02d}{d:02d}",
            f"{y}{m}{d}",
            f"{y:04d}{m:02d}{d:02d}",
        ]
    return [_digits(expected)]


def _token_forms(field: str, text: str) -> list[str]:
    if field == "invoice_number":
        return [_compact(text)]
    return [_digits(text)]


def classify_field(
    field: str,
    expected: Any,
    evidence: list[dict[str, Any]],
    parsed_fields: dict[str, Any],
) -> dict[str, Any]:
    expected_forms = [x for x in _expected_forms(field, expected) if x]
    parsed = parsed_fields.get(field)
    parsed_match = (
        _compact(parsed) == _compact(expected)
        if field == "invoice_number"
        else _digits(parsed) in expected_forms
    )

    exact = []
    near = []
    for token in evidence:
        for tf in _token_forms(field, token.get("text") or ""):
            if not tf:
                continue
            if any(exp in tf or tf in exp for exp in expected_forms):
                exact.append(token)
                break
            distance = min((_edit_distance(tf, exp) for exp in expected_forms), default=999)
            if distance <= 1 and max(len(tf), max(map(len, expected_forms), default=0)) >= 3:
                near.append({**token, "edit_distance": distance})
                break

    if parsed_match:
        category = "parsed_correct"
    elif exact:
        category = "parser_or_layout_miss"
    elif near:
        category = "recognizer_near_miss"
    else:
        category = "detector_or_recognizer_miss"

    return {
        "field": field,
        "expected": expected,
        "parsed": parsed,
        "category": category,
        "exact_token_count": len(exact),
        "near_token_count": len(near),
        "evidence": [
            {
                "text": x.get("text"),
                "confidence": x.get("confidence"),
                "box": x.get("box"),
            }
            for x in (exact[:3] or near[:3])
        ],
    }


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 invoice-ocr-diff/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
    if not data or len(data) > 12 * 1024 * 1024:
        raise RuntimeError("invalid_image")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    engine = RapidOCR()
    rows = []
    counts: dict[str, int] = {}

    for case in manifest["cases"]:
        fixture = case.get("fixture_path")
        if fixture and (root / fixture).is_file():
            image = (root / fixture).read_bytes()
        else:
            image = fetch(case["image_url"])

        evidence, _, page_conf = ocr_page_evidence(engine, image)
        parsed = extract_template_invoice(image)
        parsed_fields = parsed.get("fields") or {}
        fields = []
        for field, expected in case.get("expected", {}).items():
            if field not in FIELDS:
                continue
            item = classify_field(field, expected, evidence, parsed_fields)
            fields.append(item)
            counts[item["category"]] = counts.get(item["category"], 0) + 1

        rows.append({
            "id": case["id"],
            "page_confidence": page_conf,
            "field_diffs": fields,
        })

    summary = {
        "schema": "invoice-ocr-failure-diff/v1",
        "cases": len(rows),
        "category_counts": counts,
        "rows": rows,
    }
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
