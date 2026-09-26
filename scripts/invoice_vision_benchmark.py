#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MODEL = os.environ.get("GEMINI_INVOICE_MODEL", "gemini-3.8-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"], "description": "Gregorian YYYY-MM-DD"},
        "buyer_name": {"type": ["string", "null"]},
        "buyer_tax_id": {"type": ["string", "null"]},
        "seller_name": {"type": ["string", "null"]},
        "seller_tax_id": {"type": ["string", "null"]},
        "amount_before_tax": {"type": ["integer", "null"]},
        "tax_amount": {"type": ["integer", "null"]},
        "total_amount": {"type": ["integer", "null"]},
        "needs_review": {"type": "boolean"},
        "uncertain_fields": {"type": "array", "items": {"type": "string"}}
    },
    "required": [
        "document_type","invoice_number","invoice_date","buyer_name","buyer_tax_id",
        "seller_name","seller_tax_id","amount_before_tax","tax_amount","total_amount",
        "needs_review","uncertain_fields"
    ],
    "additionalProperties": False
}

PROMPT = """You are extracting fields from a photographed Taiwanese uniform invoice.
Read the actual document image, including handwriting. Do not guess hidden or illegible values.
Rules:
- invoice_number is two uppercase letters plus eight digits, or null.
- invoice_date must be Gregorian YYYY-MM-DD. Convert ROC year by adding 1911.
- Monetary fields are integer New Taiwan Dollars without commas.
- If a value is not visually supported, return null and include that field in uncertain_fields.
- needs_review must be true whenever any core field is uncertain.
- Never infer a monetary value only because numbers happen to satisfy arithmetic.
Return only the requested JSON structure."""

def fetch_image(image_url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(
        image_url,
        headers={"User-Agent": "Mozilla/5.0 invoice-benchmark/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
        mime = (response.headers.get_content_type() or "image/jpeg").lower()
    if not data or len(data) > 12 * 1024 * 1024:
        raise RuntimeError("invalid_image_size")
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise RuntimeError("unsupported_image_mime:" + mime)
    return data, mime


def call_gemini(api_key: str, model: str, image_url: str) -> dict[str, Any]:
    image_bytes, image_mime = fetch_image(image_url)
    body = {
        "model": model,
        "input": [
            {"type": "text", "text": PROMPT},
            {
                "type": "image",
                "data": base64.b64encode(image_bytes).decode("ascii"),
                "mime_type": image_mime,
            }
        ],
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": SCHEMA
        },
        "generation_config": {"thinking_level": "minimal"}
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "Api-Revision": "2026-05-20",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"gemini_http_{exc.code}:{detail[:1200]}") from exc

    text = payload.get("output_text")
    if not text:
        for step in payload.get("steps") or []:
            if step.get("type") != "model_output":
                continue
            for content in step.get("content") or []:
                if content.get("type") == "text" and content.get("text"):
                    text = content["text"]
                    break
            if text:
                break
    if not text:
        raise RuntimeError("missing_output_text:" + json.dumps(payload, ensure_ascii=False)[:1200])
    return json.loads(text)

def norm(v: Any) -> Any:
    if isinstance(v, str):
        return v.replace(" ", "").replace(",", "").upper()
    return v

def score(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    correct = 0
    for field, exp in expected.items():
        got = actual.get(field)
        ok = norm(got) == norm(exp)
        checks[field] = {"expected": exp, "actual": got, "ok": ok}
        correct += int(ok)
    unsafe = []
    for field in ("invoice_number","invoice_date","amount_before_tax","tax_amount","total_amount"):
        got = actual.get(field)
        if got not in (None, "") and field in expected and norm(got) != norm(expected[field]):
            if field not in (actual.get("uncertain_fields") or []):
                unsafe.append(field)
    return {
        "correct": correct,
        "total": len(expected),
        "checks": checks,
        "unsafe_fields": unsafe,
        "unsafe_pass": bool(unsafe),
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("benchmark_status=CREDENTIAL_MISSING provider=gemini env=GEMINI_API_KEY")
        return 2

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows = []
    total_correct = total_fields = unsafe_count = 0
    for case in manifest["cases"]:
        try:
            actual = call_gemini(key, args.model, case["image_url"])
            scored = score(case["expected"], actual)
            row = {"id": case["id"], "actual": actual, "score": scored}
            total_correct += scored["correct"]
            total_fields += scored["total"]
            unsafe_count += int(scored["unsafe_pass"])
            print(json.dumps(row, ensure_ascii=False))
            rows.append(row)
        except Exception as exc:
            row = {"id": case["id"], "error": type(exc).__name__ + ":" + str(exc)}
            print(json.dumps(row, ensure_ascii=False))
            rows.append(row)

    error_count=sum(1 for row in rows if row.get("error"))
    summary = {
        "model": args.model,
        "cases": len(rows),
        "errors": error_count,
        "field_exact_match": (total_correct / total_fields) if total_fields else 0.0,
        "unsafe_pass_cases": unsafe_count,
        "rows": rows,
    }
    print("benchmark_summary=" + json.dumps(summary, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if error_count == len(rows):
        return 3
    return 1 if unsafe_count else 0

if __name__ == "__main__":
    raise SystemExit(main())
