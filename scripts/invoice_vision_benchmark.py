#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MODEL = os.environ.get("GEMINI_INVOICE_MODEL", "gemini-3.8-flash")

# Share the exact production prompt, schema and transport.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.invoice_intake.vision_ocr import PROMPT, SCHEMA, read_invoice

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
    return read_invoice(image_bytes, api_key=api_key, model=model)["payload"]

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
    inputs = ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest")
    inputs.add_argument("--image", help="Local immutable original: compare both readers without DB writes")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.image:
        from dataclasses import asdict
        from services.invoice_intake.invoice_core import extract_invoice
        os.environ['INVOICE_VISION_MODE'] = 'shadow'
        os.environ['GEMINI_INVOICE_MODEL'] = args.model
        result = asdict(extract_invoice(Path(args.image).read_bytes()))
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(rendered, encoding='utf-8')
        else:
            print(rendered)
        return 0 if result['raw']['vision']['status'] == 'SUCCEEDED' else 2

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
