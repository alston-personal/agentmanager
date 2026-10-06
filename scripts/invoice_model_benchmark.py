#!/usr/bin/env python3
"""Provider-neutral benchmark for invoice OCR/VLM recognition quality."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

MONEY_FIELDS = {"amount_before_tax", "tax_amount", "total_amount"}
CORE_FIELDS = {
    "invoice_number", "invoice_date", "buyer_tax_id", "seller_tax_id",
    "amount_before_tax", "tax_amount", "total_amount",
}

PROMPT = """Read this Taiwanese invoice image. Return JSON only.
Extract invoice_number, invoice_date (Gregorian YYYY-MM-DD), buyer_tax_id,
seller_tax_id, amount_before_tax, tax_amount, total_amount.
Amounts are integer NTD. Preserve visible handwritten values. If a value is
readable but uncertain, still return the value and include its field name in
uncertain_fields. Do not invent values. Include uncertain_fields as an array.
"""

def norm(v: Any) -> Any:
    if isinstance(v, str):
        return re.sub(r"[\s,]", "", v).upper()
    return v

def score(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    correct = total = 0
    money_correct = money_total = 0
    for field, exp in expected.items():
        if field not in CORE_FIELDS:
            continue
        got = actual.get(field)
        ok = norm(got) == norm(exp)
        checks[field] = {"expected": exp, "actual": got, "ok": ok}
        total += 1
        correct += int(ok)
        if field in MONEY_FIELDS:
            money_total += 1
            money_correct += int(ok)
    return {
        "checks": checks,
        "correct": correct,
        "total": total,
        "field_exact_match": correct / total if total else 0.0,
        "money_correct": money_correct,
        "money_total": money_total,
        "money_exact_match": money_correct / money_total if money_total else None,
    }

def load_bytes(case: dict[str, Any], root: Path) -> tuple[bytes, str]:
    fixture = case.get("fixture_path")
    if fixture:
        path = root / fixture
        if path.is_file():
            data = path.read_bytes()
            suffix = path.suffix.lower()
            mime = "image/png" if suffix == ".png" else "image/jpeg"
            return data, mime
    url = case.get("image_url")
    if not url:
        raise RuntimeError("image_missing")
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 invoice-model-benchmark/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(12 * 1024 * 1024 + 1)
        mime = response.headers.get_content_type() or "image/jpeg"
    if not data or len(data) > 12 * 1024 * 1024:
        raise RuntimeError("invalid_image")
    return data, mime

def run_rapidocr(image: bytes) -> dict[str, Any]:
    from rapidocr import RapidOCR
    from scripts.invoice_rapidocr_benchmark import result_text
    engine = RapidOCR()
    text = result_text(engine(image))
    # RapidOCR is raw-text baseline. Report evidence presence rather than
    # pretending it performs structured semantic extraction.
    digits = re.sub(r"\D", "", text)
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    return {"_raw_text": text[:5000], "_digits": digits, "_compact": compact}

def rapidocr_score(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    text = actual.get("_raw_text", "")
    digits = re.sub(r"\D", "", text)
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    checks = {}
    correct = total = money_correct = money_total = 0
    for field, exp in expected.items():
        if field not in CORE_FIELDS:
            continue
        if field == "invoice_number":
            ok = re.sub(r"[^A-Z0-9]", "", str(exp).upper()) in compact
        elif field == "invoice_date":
            y, m, d = [int(x) for x in str(exp).split("-")]
            roc = y - 1911
            candidates = {f"{roc}{m}{d}", f"{roc:03d}{m:02d}{d:02d}", f"{y}{m}{d}", f"{y:04d}{m:02d}{d:02d}"}
            ok = any(x in digits for x in candidates)
        else:
            ok = re.sub(r"\D", "", str(exp)) in digits
        checks[field] = {"expected": exp, "actual": None, "ok": ok}
        total += 1; correct += int(ok)
        if field in MONEY_FIELDS:
            money_total += 1; money_correct += int(ok)
    return {
        "checks": checks,
        "correct": correct,
        "total": total,
        "field_exact_match": correct / total if total else 0.0,
        "money_correct": money_correct,
        "money_total": money_total,
        "money_exact_match": money_correct / money_total if money_total else None,
    }

def run_gemini(image: bytes, model: str) -> dict[str, Any]:
    from services.invoice_intake.vision_ocr import read_invoice
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY_missing")
    return read_invoice(image, api_key=key, model=model)["payload"]

def run_openai_compatible(image: bytes, mime: str, model: str) -> dict[str, Any]:
    endpoint = os.environ.get("INVOICE_VLM_ENDPOINT", "").strip().rstrip("/")
    key = os.environ.get("INVOICE_VLM_API_KEY", "").strip()
    if not endpoint:
        raise RuntimeError("INVOICE_VLM_ENDPOINT_missing")
    url = endpoint if endpoint.endswith("/chat/completions") else endpoint + "/v1/chat/completions"
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
                }},
            ],
        }],
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        envelope = json.loads(response.read(1024 * 1024 + 1))
    text = envelope["choices"][0]["message"]["content"]
    return json.loads(text)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--provider", choices=["rapidocr", "gemini", "openai-compatible"], required=True)
    ap.add_argument("--model", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows = []
    field_correct = field_total = money_correct = money_total = errors = 0
    for case in manifest["cases"]:
        try:
            image, mime = load_bytes(case, root)
            if args.provider == "rapidocr":
                actual = run_rapidocr(image)
                scored = rapidocr_score(case["expected"], actual)
            elif args.provider == "gemini":
                model = args.model or os.environ.get("GEMINI_INVOICE_MODEL", "gemini-3.8-flash")
                actual = run_gemini(image, model)
                scored = score(case["expected"], actual)
            else:
                if not args.model:
                    raise RuntimeError("--model_required")
                actual = run_openai_compatible(image, mime, args.model)
                scored = score(case["expected"], actual)

            rows.append({"id": case["id"], "score": scored})
            field_correct += scored["correct"]; field_total += scored["total"]
            money_correct += scored["money_correct"]; money_total += scored["money_total"]
        except Exception as exc:
            errors += 1
            rows.append({"id": case["id"], "error": type(exc).__name__ + ":" + str(exc)})

    summary = {
        "schema": "invoice-model-benchmark/v1",
        "provider": args.provider,
        "model": args.model or None,
        "cases": len(rows),
        "errors": errors,
        "field_exact_match": field_correct / field_total if field_total else 0.0,
        "money_exact_match": money_correct / money_total if money_total else None,
        "rows": rows,
    }
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    return 0 if errors < len(rows) else 2

if __name__ == "__main__":
    raise SystemExit(main())
