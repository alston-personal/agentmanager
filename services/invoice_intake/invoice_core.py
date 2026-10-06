from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
from services.invoice_intake.template_ocr import extract_template_invoice, valid_tax_id, seller_region_text, tax_id_candidates
from services.invoice_intake import vision_ocr
from capabilities.stamp_recognition.runtime import StampStore, detect_stamp_regions, fingerprint_stamp
from capabilities.ocr_memory import OCRMemoryStore, context_from_extraction

ESSENTIAL_FIELDS = ("invoice_number", "invoice_date", "amount_before_tax", "total_amount")


def classify_review(
    fields: dict[str, Any],
    confidence: dict[str, float],
    *,
    derived_amounts: bool = False,
    stamp_recognition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return field-level review guidance without conflating uncertainty with failure."""
    hard_fields: list[str] = []
    quick_fields: list[str] = []
    reasons: list[str] = []

    for key in ESSENTIAL_FIELDS:
        if fields.get(key) in (None, ""):
            hard_fields.append(key)
            reasons.append(f"missing:{key}")
        elif confidence.get(key, 0.0) < 0.80:
            hard_fields.append(key)
            reasons.append(f"low_confidence:{key}")

    for key in ("vendor_name", "seller_tax_id"):
        if fields.get(key) in (None, ""):
            hard_fields.append(key)
            reasons.append(f"missing:{key}")

    vendor_conf = confidence.get("vendor_name", 0.0)
    if fields.get("vendor_name") not in (None, "") and vendor_conf < 0.80:
        quick_fields.append("vendor_name")
        reasons.append("confirm:vendor_name")

    seller_conf = confidence.get("seller_tax_id", 0.0)
    if fields.get("seller_tax_id") not in (None, "") and seller_conf < 0.80:
        quick_fields.append("seller_tax_id")
        reasons.append("confirm:seller_tax_id")

    if derived_amounts:
        for key in ("amount_before_tax", "tax_amount", "total_amount"):
            if fields.get(key) not in (None, "") and key not in quick_fields:
                quick_fields.append(key)
        reasons.append("confirm:derived_amounts")

    stamp = stamp_recognition or {}
    decision = stamp.get("decision")
    if decision in {"unknown_stamp", "uncertain"} and fields.get("vendor_name") and fields.get("seller_tax_id"):
        for key in ("vendor_name", "seller_tax_id"):
            if key not in quick_fields:
                quick_fields.append(key)
        reasons.append(f"confirm:stamp_{decision}")

    hard_fields = list(dict.fromkeys(hard_fields))
    quick_fields = [x for x in dict.fromkeys(quick_fields) if x not in hard_fields]

    meaningful_fields = (
        "invoice_number", "invoice_date", "vendor_name", "seller_tax_id",
        "amount_before_tax", "total_amount",
    )
    meaningful_count = sum(fields.get(key) not in (None, "") for key in meaningful_fields)

    if meaningful_count <= 2:
        status = "recognition_insufficient"
        reasons.append("recognition:insufficient_fields")
    elif hard_fields:
        status = "needs_review"
    elif quick_fields:
        status = "quick_confirm"
    else:
        status = "extracted"

    return {
        "status": status,
        "required_fields": hard_fields,
        "confirm_fields": quick_fields,
        "reasons": reasons,
    }


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def processing_is_stale(status: str | None, updated_at: str | None, *, threshold_seconds: int = 120) -> bool:
    if status != "processing" or not updated_at:
        return False
    try:
        stamp = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    return age >= threshold_seconds


def normalize_invoice_number(text: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    for match in re.finditer(r"[A-Z0-9]{10}", compact):
        token = match.group(0)
        prefix = token[:2]
        digits = token[2:]
        digits = digits.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "G": "6", "Z": "2"}))
        if re.fullmatch(r"[A-Z]{2}", prefix) and re.fullmatch(r"\d{8}", digits):
            return prefix + digits
    for match in re.finditer(r"([A-Z]{2})\s*([0-9OILSBGZ][0-9OILSBGZ\s-]{7,12})", text.upper()):
        digits = re.sub(r"[^0-9OILSBGZ]", "", match.group(2))
        digits = digits.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "G": "6", "Z": "2"}))
        if len(digits) >= 8 and digits[:8].isdigit():
            return match.group(1) + digits[:8]
    return None


def normalize_roc_date(text: str) -> str | None:
    nums = [int(x) for x in re.findall(r"\d{1,4}", text)]
    candidates: list[tuple[int, int, int]] = []
    for i in range(max(0, len(nums) - 2)):
        y, m, d = nums[i:i+3]
        if 1 <= m <= 12 and 1 <= d <= 31:
            if 90 <= y <= 199:
                candidates.append((y + 1911, m, d))
            elif 2000 <= y <= 2200:
                candidates.append((y, m, d))
    compact = re.sub(r"\D", "", text)
    if not candidates and len(compact) in (6, 7):
        for y_len in (3, 4):
            if len(compact) <= y_len + 2:
                continue
            y = int(compact[:y_len])
            rest = compact[y_len:]
            for m_len in (1, 2):
                if len(rest) <= m_len:
                    continue
                m = int(rest[:m_len])
                d = int(rest[m_len:])
                yy = y + 1911 if 90 <= y <= 199 else y
                if 2000 <= yy <= 2200 and 1 <= m <= 12 and 1 <= d <= 31:
                    candidates.append((yy, m, d))
    for y, m, d in candidates:
        try:
            return datetime(y, m, d).date().isoformat()
        except ValueError:
            continue
    return None


VENDOR_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9·・()（）&\-]{2,32}(?:股份有限公司|有限公司|企業社|商行|實業社|工作室|餐廳|飯店|旅店|商店|門市|分店|公司|行|店))"
)


def normalize_vendor_name(text: str) -> str | None:
    blocked = (
        "統一發票", "發票", "收執聯", "扣抵聯", "存根聯", "營業稅",
        "銷售額", "合計", "總計", "買受人", "銷售人", "統一編號",
    )
    candidates: list[str] = []
    for line in (text or "").splitlines():
        compact = re.sub(r"\s+", "", line).strip("：:-—")
        if not compact or any(token in compact for token in blocked):
            continue
        for m in VENDOR_SUFFIX_RE.finditer(compact):
            name = m.group(1).strip()
            if 2 <= len(name) <= 36 and name not in candidates:
                candidates.append(name)
    if not candidates:
        return None
    candidates.sort(key=lambda x: (len(x), x.count("公司")), reverse=True)
    return candidates[0]


def money_values(text: str) -> list[int]:
    out: list[int] = []
    for raw in re.findall(r"(?<!\d)\d[\d,\.\s]{1,12}(?!\d)", text):
        cleaned = re.sub(r"[^0-9]", "", raw)
        if 2 <= len(cleaned) <= 9:
            value = int(cleaned)
            if 0 < value < 1_000_000_000:
                out.append(value)
    return out


def extract_line_items_from_text(text: str) -> list[dict[str, Any]]:
    """Best-effort line item candidates from OCR text; never invent values."""
    items: list[dict[str, Any]] = []
    blocked = ("發票", "銷售額", "營業稅", "總計", "合計", "統一編號", "日期", "買受人", "銷售人")
    for line in (text or "").splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        if not clean or any(token in clean for token in blocked):
            continue
        nums = []
        for raw in re.findall(r"(?<!\d)\d[\d,.]*(?!\d)", clean):
            digits = re.sub(r"[^0-9]", "", raw)
            value = int(digits) if digits else None
            if value is not None:
                nums.append((raw, value))
        if len(nums) < 3:
            continue
        quantity, unit_price, amount = [x[1] for x in nums[-3:]]
        if quantity <= 0 or unit_price < 0 or amount <= 0:
            continue
        tolerance = max(1, round(amount * 0.02))
        if abs(quantity * unit_price - amount) > tolerance:
            continue
        first_numeric = clean.find(nums[-3][0])
        description = clean[:first_numeric].strip(" :-—")
        if not description or len(description) > 80:
            continue
        items.append({
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
            "confidence": 0.72,
        })
    return items


def choose_amounts(texts: list[str]) -> tuple[int | None, int | None, int | None, float]:
    best: tuple[int | None, int | None, int | None, float] = (None, None, None, 0.0)
    for text in texts:
        vals = money_values(text)
        for i, a in enumerate(vals):
            for j in range(i + 1, len(vals)):
                b = vals[j]
                for k in range(j + 1, len(vals)):
                    c = vals[k]
                    if a + b == c and a >= b and c >= 100:
                        return a, b, c, 0.98
        unique = []
        for v in vals:
            if v not in unique:
                unique.append(v)
        if len(unique) >= 2:
            for a in unique:
                for c in unique:
                    if c <= a:
                        continue
                    tax = c - a
                    if tax > 0 and abs(tax - round(a * 0.05)) <= 2:
                        best = (a, tax, c, 0.84)
    return best


def ocr_image(
    image: Image.Image,
    *,
    psm: int,
    whitelist: str | None = None,
    lang: str = "eng",
    timeout_seconds: float | None = None,
) -> str:
    prepared = ImageOps.autocontrast(ImageOps.grayscale(image))
    prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
    prepared = ImageEnhance.Contrast(prepared).enhance(1.35)
    cmd = ["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    payload = BytesIO()
    prepared.save(payload, format="PNG")
    if timeout_seconds is None:
        timeout_seconds = float(os.environ.get("INVOICE_TESSERACT_TIMEOUT_SECONDS", "4"))
    timeout_seconds = max(1.0, min(20.0, float(timeout_seconds)))
    try:
        proc = subprocess.run(
            cmd,
            input=payload.getvalue(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""


def crop_rel(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    l, t, r, b = box
    return image.crop((int(w*l), int(h*t), int(w*r), int(h*b)))


def crop_abs(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    l, t, r, b = box
    return image.crop((max(0,l), max(0,t), min(image.width,r), min(image.height,b)))


def stamp_variants(image: Image.Image) -> list[Image.Image]:
    """Return OCR-friendly variants for red/blue/black stamps on white paper."""
    rgb = image.convert("RGB")
    r, g, b = rgb.split()
    variants = [
        ImageOps.autocontrast(ImageOps.grayscale(rgb)),
        ImageOps.autocontrast(r),
        ImageOps.autocontrast(g),
        ImageOps.autocontrast(b),
    ]
    # Red stamps are usually much darker in G/B than the white paper;
    # blue stamps are often strongest in R/G. Channel variants make those
    # strokes survive even when grayscale contrast is weak.
    return variants


def ocr_stamp_text(
    image: Image.Image,
    *,
    digits_only: bool = False,
    fast: bool = False,
    timeout_seconds: float | None = None,
) -> list[str]:
    texts: list[str] = []
    whitelist = "0123456789" if digits_only else None
    lang = "eng" if digits_only else "chi_tra+eng"
    variants = stamp_variants(image)
    if fast:
        variants = variants[:2]
    psms = (6, 11) if fast else (6, 11, 12)
    for variant in variants:
        for psm in psms:
            text = ocr_image(
                variant,
                psm=psm,
                whitelist=whitelist,
                lang=lang,
                timeout_seconds=timeout_seconds,
            )
            if text.strip() and text not in texts:
                texts.append(text)
    return texts


def stamp_assist_with_budget(
    image_bytes: bytes,
    stamp_store: StampStore | None,
    *,
    budget_ms: int = 100,
) -> dict[str, Any]:
    """Best-effort stamp lookup that can never block the invoice critical path.

    The worker may continue briefly after timeout, but its result is discarded.
    Main OCR/fallback never depends on this function succeeding.
    """
    if stamp_store is None:
        return {"status": "UNAVAILABLE", "latency_ms": 0.0}

    result: dict[str, Any] = {}
    done = threading.Event()
    started = time.perf_counter()

    def worker() -> None:
        try:
            regions = detect_stamp_regions(image_bytes)
            if not regions:
                result.update({"status": "NO_STAMP_CANDIDATE", "regions": []})
                return
            region = regions[0]
            fp = fingerprint_stamp(image_bytes, region)
            match = stamp_store.match(fp)
            payload = {
                "status": "NO_MATCH",
                "regions": [{
                    "box": list(region.box),
                    "confidence": region.confidence,
                    "color_hint": region.color_hint,
                }],
                "decision": match.decision,
                "score": match.score,
                "stamp_id": match.stamp_id,
                "entity_id": match.entity_id,
                "algorithm": fp.algorithm,
                "version": fp.version,
            }
            if match.decision == "same_stamp" and match.stamp_id:
                payload["status"] = "MATCHED_CONFIRMED"
                payload["remembered_attributes"] = stamp_store.resolve_verified_attributes(match.stamp_id)
            result.update(payload)
        except Exception as exc:
            result.update({"status": "ERROR", "error_type": type(exc).__name__})
        finally:
            done.set()

    threading.Thread(
        target=worker,
        name="invoice-stamp-assist",
        daemon=True,
    ).start()
    done.wait(max(0.0, budget_ms / 1000.0))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    if not done.is_set():
        return {"status": "TIMEOUT", "latency_ms": latency_ms, "budget_ms": budget_ms}
    result["latency_ms"] = latency_ms
    result["budget_ms"] = budget_ms
    return result


def deep_tax_id_from_regions(
    images: list[Image.Image],
    *,
    deadline: float,
    timeout_seconds: float = 10.0,
) -> tuple[str | None, list[str]]:
    """Progressively OCR seller regions until a valid tax id is found.

    This is baseline OCR, not stamp recognition. It first uses RapidOCR on
    enlarged regions for text detection, then falls back to channel-specific
    Tesseract attempts while respecting the caller's wall-clock budget.
    """
    texts: list[str] = []

    try:
        from rapidocr import RapidOCR
        engine = RapidOCR()
    except Exception:
        engine = None

    for image in images:
        if time.perf_counter() >= deadline:
            return None, texts

        if engine is not None:
            enlarged = image.resize((image.width * 3, image.height * 3))
            buf = BytesIO()
            enlarged.save(buf, format="PNG")
            try:
                result = engine(buf.getvalue())
                rapid_texts = []
                if hasattr(result, "txts") and result.txts is not None:
                    rapid_texts = [str(x) for x in result.txts]
                elif hasattr(result, "to_json"):
                    obj = result.to_json()
                    if isinstance(obj, str):
                        obj = json.loads(obj)
                    obj = obj or {}
                    rapid_texts = [str(x) for x in (
                        obj.get("txts") or obj.get("texts") or obj.get("rec_texts") or []
                    )]
                rapid_text = "\n".join(rapid_texts)
                if rapid_text.strip():
                    texts.append(rapid_text)
                valid = [v for v in tax_id_candidates(rapid_text) if valid_tax_id(v)]
                if valid:
                    return valid[0], texts
            except Exception:
                pass

        for variant in stamp_variants(image):
            for psm in (6, 11, 12):
                if time.perf_counter() >= deadline:
                    return None, texts
                text = ocr_image(
                    variant,
                    psm=psm,
                    whitelist="0123456789",
                    lang="eng",
                    timeout_seconds=timeout_seconds,
                )
                if text.strip():
                    texts.append(text)
                candidates: list[str] = []
                for candidate in re.findall(r"(?<!\d)\d{8}(?!\d)", re.sub(r"\s+", "", text)):
                    if candidate not in candidates:
                        candidates.append(candidate)
                valid = [value for value in candidates if valid_tax_id(value)]
                if valid:
                    return valid[0], texts
    return None, texts


def deep_fallback_enrich(
    image_bytes: bytes,
    base: "Extraction",
    *,
    budget_seconds: float = 60.0,
) -> "Extraction":
    """Best-effort second-stage OCR based on the previously usable #1109 search pattern.

    It only fills fields still missing from the fast pass, never waits on stamp
    recognition, and stops launching new OCR work once the wall-clock budget is
    exhausted. This is intended for background enrichment after a fast result is
    already visible to the user.
    """
    started = time.perf_counter()
    deadline = started + max(1.0, budget_seconds)
    image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    fields = dict(base.fields)
    confidence = dict(base.confidence)
    raw = json.loads(json.dumps(base.raw, ensure_ascii=False))
    deep = {
        "status": "running",
        "started_from_status": (raw.get("review") or {}).get("status"),
        "fallback_used": [],
    }
    raw["deep_fallback"] = deep

    deep_timeout = max(
        1.0,
        min(20.0, float(os.environ.get("INVOICE_DEEP_TESSERACT_TIMEOUT_SECONDS", "10"))),
    )

    def within_budget() -> bool:
        return time.perf_counter() < deadline

    invoice_crop = crop_rel(image, (0.12, 0.02, 0.43, 0.22))
    date_crop = crop_rel(image, (0.43, 0.11, 0.79, 0.30))
    amount_crop = crop_rel(image, (0.46, 0.31, 0.73, 0.86))

    if not fields.get("invoice_number") and within_budget():
        texts = []
        for psm in (7, 6, 11):
            if not within_budget():
                break
            texts.append(ocr_image(
                invoice_crop,
                psm=psm,
                whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                timeout_seconds=deep_timeout,
            ))
        value = next((normalize_invoice_number(x) for x in texts if normalize_invoice_number(x)), None)
        if value:
            fields["invoice_number"] = value
            confidence["invoice_number"] = max(confidence.get("invoice_number", 0.0), 0.95)
        deep["fallback_used"].append("invoice_number")

    if not fields.get("invoice_date") and within_budget():
        texts = []
        for psm in (6, 11):
            if not within_budget():
                break
            texts.append(ocr_image(
                date_crop,
                psm=psm,
                whitelist="0123456789/-",
                timeout_seconds=deep_timeout,
            ))
        value = next((normalize_roc_date(x) for x in texts if normalize_roc_date(x)), None)
        if value:
            fields["invoice_date"] = value
            confidence["invoice_date"] = max(confidence.get("invoice_date", 0.0), 0.90)
        deep["fallback_used"].append("invoice_date")

    if any(fields.get(k) is None for k in ("amount_before_tax", "tax_amount", "total_amount")) and within_budget():
        amount_texts: list[str] = []
        regions = [
            amount_crop,
            crop_rel(image, (0.18, 0.24, 0.95, 0.90)),
            crop_rel(image, (0.04, 0.42, 0.96, 0.97)),
            image,
        ]
        for region in regions:
            for psm in (6, 11):
                if not within_budget():
                    break
                amount_texts.append(ocr_image(
                    region,
                    psm=psm,
                    whitelist="0123456789,.-",
                    timeout_seconds=deep_timeout,
                ))
            if not within_budget():
                break
        subtotal, tax, total, amount_conf = choose_amounts(amount_texts)
        for key, value in {
            "amount_before_tax": subtotal,
            "tax_amount": tax,
            "total_amount": total,
        }.items():
            if fields.get(key) is None and value is not None:
                fields[key] = value
                confidence[key] = max(confidence.get(key, 0.0), amount_conf)
        deep["fallback_used"].append("amounts")

    if not fields.get("seller_tax_id") and within_budget():
        # Deep fallback owns this fixed seller/stamp crop. It progressively
        # expands OCR effort and stops immediately once a valid tax id appears.
        seller_regions = [
            crop_rel(image, (0.45, 0.30, 1.00, 1.00)),
            crop_rel(image, (0.60, 0.38, 0.98, 0.96)),
        ]
        chosen, texts = deep_tax_id_from_regions(
            seller_regions,
            deadline=deadline,
            timeout_seconds=deep_timeout,
        )
        if chosen:
            fields["seller_tax_id"] = chosen
            confidence["seller_tax_id"] = max(
                confidence.get("seller_tax_id", 0.0),
                0.88,
            )
        deep["seller_tax_id_texts"] = texts
        deep["fallback_used"].append("seller_tax_id_progressive")

    if not fields.get("vendor_name") and within_budget():
        rapid_text = ((raw.get("template") or {}).get("raw_text") or "")
        vendor_texts = [rapid_text]
        if within_budget():
            vendor_texts.append(
                ocr_image(
                    crop_rel(image, (0.02, 0.00, 0.98, 0.34)),
                    psm=6,
                    lang="chi_tra+eng",
                    timeout_seconds=deep_timeout,
                )
            )
        if within_budget():
            vendor_texts.extend(
                ocr_stamp_text(
                    crop_rel(image, (0.42, 0.42, 0.99, 0.99)),
                    fast=False,
                    timeout_seconds=deep_timeout,
                )
            )
        vendor = next((normalize_vendor_name(x) for x in vendor_texts if normalize_vendor_name(x)), None)
        if vendor:
            fields["vendor_name"] = vendor
            confidence["vendor_name"] = max(confidence.get("vendor_name", 0.0), 0.78)
        deep["fallback_used"].append("vendor_name")

    template = raw.get("template") or {}
    derived_amounts = bool(
        template.get("matched")
        and template.get("document_type") == "three_part_uniform_invoice"
        and not bool(template.get("visual_amounts"))
    )
    review = classify_review(
        fields,
        confidence,
        derived_amounts=derived_amounts,
        stamp_recognition=raw.get("stamp_recognition") or {},
    )
    raw["review"] = review
    deep["status"] = "completed" if within_budget() else "budget_exhausted"
    deep["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    deep["result_status"] = review["status"]
    raw.setdefault("timings_ms", {})["deep_fallback_ms"] = deep["elapsed_ms"]
    raw["engine"] = str(raw.get("engine") or "rapidocr-template-v1") + "+deep-fallback"
    return Extraction(
        fields=fields,
        confidence=confidence,
        raw=raw,
        review_required=review["status"] != "extracted",
    )


@dataclass
class Extraction:
    fields: dict[str, Any]
    confidence: dict[str, float]
    raw: dict[str, Any]
    review_required: bool


def extract_legacy_invoice(
    image_bytes: bytes,
    *,
    stamp_store: StampStore | None = None,
    ocr_memory: OCRMemoryStore | None = None,
) -> Extraction:
    """Template-first production extraction with legacy Tesseract fallback.

    Known Taiwan invoice/receipt layouts use RapidOCR + semantic validation first.
    Tesseract only fills fields that remain unresolved; it never overwrites a
    higher-confidence template result.
    """
    total_started = time.perf_counter()
    timings_ms: dict[str, float] = {}
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")

    rapid_started = time.perf_counter()
    rapid = extract_template_invoice(image_bytes)
    timings_ms["template_ocr_ms"] = round((time.perf_counter() - rapid_started) * 1000, 1)
    fields = {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "buyer_tax_id": None,
        "seller_tax_id": None,
        "amount_before_tax": None,
        "tax_amount": None,
        "total_amount": None,
    }
    confidence = {k: 0.0 for k in fields}
    local_line_items = extract_line_items_from_text(rapid.get("raw_text") or "")
    raw: dict[str, Any] = {
        "engine": "rapidocr-template-v1+tesseract-fallback",
        "template": rapid,
        "fallback_used": [],
        "image_size": list(image.size),
        "line_items": local_line_items,
    }

    if rapid.get("matched"):
        for key, value in (rapid.get("fields") or {}).items():
            if key in fields and value not in (None, ""):
                fields[key] = value
                confidence[key] = float((rapid.get("confidence") or {}).get(key) or 0.0)

    # Stamp recognition is optional enrichment only. It has a tiny wall-clock
    # budget and can never influence whether baseline OCR/fallback runs.
    stamp_mode = str(os.environ.get("INVOICE_STAMP_ASSIST_MODE", "legacy")).strip().lower()
    if stamp_mode not in {"legacy", "shadow", "active"}:
        stamp_mode = "legacy"
    if stamp_mode == "legacy":
        stamp_result = {"mode": stamp_mode, "status": "DISABLED_BASELINE", "latency_ms": 0.0}
    else:
        budget_ms = max(10, min(500, int(os.environ.get("INVOICE_STAMP_ASSIST_BUDGET_MS", "100"))))
        stamp_result = stamp_assist_with_budget(image_bytes, stamp_store, budget_ms=budget_ms)
        stamp_result["mode"] = stamp_mode
    raw["stamp_recognition"] = stamp_result

    if stamp_mode == "active" and stamp_result.get("status") == "MATCHED_CONFIRMED":
        remembered = stamp_result.get("remembered_attributes") or {}
        if not fields["vendor_name"] and remembered.get("vendor_name"):
            fields["vendor_name"] = remembered["vendor_name"]
            confidence["vendor_name"] = 0.99
        if not fields["seller_tax_id"] and remembered.get("seller_tax_id"):
            fields["seller_tax_id"] = remembered["seller_tax_id"]
            confidence["seller_tax_id"] = 0.99

    timings_ms["stamp_detect_match_ms"] = float(stamp_result.get("latency_ms") or 0.0)

    # Legacy crops remain as a recovery path only.
    fallback_started = time.perf_counter()
    invoice_crop = crop_rel(image, (0.12, 0.02, 0.43, 0.22))
    date_crop = crop_rel(image, (0.43, 0.11, 0.79, 0.30))
    amount_crop = crop_rel(image, (0.46, 0.31, 0.73, 0.86))
    # Baseline seller fallback owns its own crop and never depends on stamp assist.
    stamp_crop = crop_rel(image, (0.60, 0.38, 0.98, 0.96))

    if not fields["invoice_number"]:
        invoice_texts = [
            ocr_image(invoice_crop, psm=7, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
            ocr_image(invoice_crop, psm=11, whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        ]
        value = next((normalize_invoice_number(x) for x in invoice_texts if normalize_invoice_number(x)), None)
        if value:
            fields["invoice_number"] = value
            confidence["invoice_number"] = 0.95
        raw["invoice_texts"] = invoice_texts
        raw["fallback_used"].append("invoice_number")

    if not fields["invoice_date"]:
        date_texts = [
            ocr_image(date_crop, psm=6, whitelist="0123456789/-"),
        ]
        value = next((normalize_roc_date(x) for x in date_texts if normalize_roc_date(x)), None)
        if value:
            fields["invoice_date"] = value
            confidence["invoice_date"] = 0.90
        raw["date_texts"] = date_texts
        raw["fallback_used"].append("invoice_date")

    if any(fields[k] is None for k in ("amount_before_tax", "tax_amount", "total_amount")):
        amount_regions = [
            amount_crop,
            crop_rel(image, (0.18, 0.24, 0.95, 0.90)),
        ]
        amount_texts = []
        for region in amount_regions:
            amount_texts.extend([
                ocr_image(region, psm=6, whitelist="0123456789,.-"),
                ocr_image(region, psm=11, whitelist="0123456789,.-"),
            ])
        subtotal, tax, total, amount_conf = choose_amounts(amount_texts)
        fallback_amounts = {
            "amount_before_tax": subtotal,
            "tax_amount": tax,
            "total_amount": total,
        }
        for key, value in fallback_amounts.items():
            if fields[key] is None and value is not None:
                fields[key] = value
                confidence[key] = amount_conf
        raw["amount_texts"] = amount_texts
        raw["fallback_used"].append("amounts")

    if not fields["seller_tax_id"]:
        # Bounded fallback: one focused Tesseract pass only. Never fan out into
        # many variants/PSMs on the synchronous recognition path.
        stamp_text = ocr_image(stamp_crop, psm=6, whitelist="0123456789", lang="eng")
        tax_ids: list[str] = []
        for candidate in re.findall(r"(?<!\d)\d{8}(?!\d)", re.sub(r"\s+", "", stamp_text)):
            if candidate not in tax_ids:
                tax_ids.append(candidate)
        valid = [x for x in tax_ids if valid_tax_id(x)]
        chosen = valid[0] if len(valid) == 1 else None
        if chosen:
            fields["seller_tax_id"] = chosen
            confidence["seller_tax_id"] = 0.86
        raw["stamp_texts"] = [stamp_text] if stamp_text else []
        raw["fallback_used"].append("seller_tax_id_bounded")

    if not fields["vendor_name"]:
        seller_text = seller_region_text(rapid.get("raw_text") or "")
        vendor_texts = [seller_text] if seller_text else []
        vendor = next((normalize_vendor_name(t) for t in vendor_texts if normalize_vendor_name(t)), None)
        if not vendor:
            vendor_stamp_text = ocr_image(stamp_crop, psm=6, lang="chi_tra+eng")
            if vendor_stamp_text:
                vendor_texts.append(vendor_stamp_text)
                vendor = normalize_vendor_name(vendor_stamp_text)
        if vendor:
            fields["vendor_name"] = vendor
            confidence["vendor_name"] = 0.78
        raw["vendor_texts"] = vendor_texts
        raw["fallback_used"].append("vendor_name_bounded")

    timings_ms["fallback_ocr_ms"] = round((time.perf_counter() - fallback_started) * 1000, 1)

    # Human-confirmed correction memory runs after ordinary OCR/stamp extraction
    # and before review classification. Strong context may correct an exact repeated
    # OCR error; weaker context is exposed only as a suggestion.
    memory_mode = str(os.environ.get("INVOICE_OCR_MEMORY_MODE", "suggest")).strip().lower()
    if memory_mode not in {"off", "suggest", "active"}:
        memory_mode = "suggest"
    raw["ocr_memory"] = {"mode": memory_mode, "applied": [], "suggestions": []}
    memory_started = time.perf_counter()
    if ocr_memory is not None and memory_mode != "off":
        memory_context = context_from_extraction(raw, fields)
        for key, observed in list(fields.items()):
            if observed in (None, ""):
                continue
            decision = ocr_memory.resolve(
                field_name=key,
                observed_value=observed,
                context=memory_context,
            )
            evidence = {
                "field": key,
                "observed": observed,
                "corrected": decision.corrected_value,
                "score": decision.score,
                "confirmed_count": decision.confirmed_count,
                "reason": decision.reason,
            }
            if (
                memory_mode == "active"
                and decision.decision == "auto_correct"
                and decision.corrected_value not in (None, "")
            ):
                fields[key] = decision.corrected_value
                confidence[key] = max(confidence.get(key, 0.0), 0.97)
                raw["ocr_memory"]["applied"].append(evidence)
            elif decision.decision in {"auto_correct", "suggest"}:
                raw["ocr_memory"]["suggestions"].append(evidence)

    timings_ms["ocr_memory_ms"] = round((time.perf_counter() - memory_started) * 1000, 1)

    # A mathematically derived 5% split is useful for assistance but is not enough
    # by itself for unattended posting; keep that case in review.
    derived_amounts = bool(
        rapid.get("matched")
        and rapid.get("document_type") == "three_part_uniform_invoice"
        and rapid.get("total_amount") is None
        and rapid.get("visual_amounts") is False
    )
    # Current template extractor exposes visual_amounts explicitly; if false while
    # all three amounts are present, they may include a tax-derived split.
    if rapid.get("matched") and rapid.get("document_type") == "three_part_uniform_invoice":
        derived_amounts = not bool(rapid.get("visual_amounts"))

    stamp_matched = (raw.get("stamp_recognition") or {}).get("status") == "MATCHED_CONFIRMED"
    memory_applied = {x["field"] for x in (raw.get("ocr_memory") or {}).get("applied", [])}
    raw["field_sources"] = {
        "invoice_number": ("ocr_memory" if "invoice_number" in memory_applied else "template_or_printed"),
        "invoice_date": ("ocr_memory" if "invoice_date" in memory_applied else "template_or_handwritten"),
        "vendor_name": ("ocr_memory" if "vendor_name" in memory_applied else
                        "stamp_registry" if stamp_matched and fields["vendor_name"] else
                        "stamp_or_printed" if fields["vendor_name"] else None),
        "seller_tax_id": ("ocr_memory" if "seller_tax_id" in memory_applied else
                          "stamp_registry" if stamp_matched and fields["seller_tax_id"] else
                          "stamp_or_printed" if fields["seller_tax_id"] else None),
        "amount_before_tax": ("ocr_memory" if "amount_before_tax" in memory_applied else "printed_or_handwritten_amount"),
        "tax_amount": ("ocr_memory" if "tax_amount" in memory_applied else "printed_or_handwritten_amount"),
        "total_amount": ("ocr_memory" if "total_amount" in memory_applied else "printed_or_handwritten_amount"),
    }

    review = classify_review(
        fields,
        confidence,
        derived_amounts=derived_amounts,
        stamp_recognition=raw.get("stamp_recognition") or {},
    )
    for suggestion in (raw.get("ocr_memory") or {}).get("suggestions", []):
        field = suggestion.get("field")
        if field and field not in review["required_fields"] and field not in review["confirm_fields"]:
            review["confirm_fields"].append(field)
            review["reasons"].append(f"confirm:ocr_memory:{field}")
    if review["required_fields"]:
        review["status"] = "needs_review"
    elif review["confirm_fields"]:
        review["status"] = "quick_confirm"
    else:
        review["status"] = "extracted"
    raw["review"] = review
    timings_ms["total_local_ms"] = round((time.perf_counter() - total_started) * 1000, 1)
    raw["timings_ms"] = timings_ms
    return Extraction(
        fields=fields,
        confidence=confidence,
        raw=raw,
        review_required=review["status"] != "extracted",
    )


def extract_invoice(
    image_bytes: bytes,
    *,
    stamp_store: StampStore | None = None,
    ocr_memory: OCRMemoryStore | None = None,
) -> Extraction:
    """Compare whole-image vision with the existing reader on identical bytes.

    off: local OCR; shadow: local fields + comparison; primary: vision fields.
    Vision candidates always require review; no guessed confidence or auto posting.
    """
    config = vision_ocr.configuration()
    legacy_error = None
    try:
        legacy = extract_legacy_invoice(image_bytes, stamp_store=stamp_store, ocr_memory=ocr_memory)
    except Exception as exc:
        if config['mode'] != 'primary' or config['status'] != 'CONFIGURED':
            raise
        legacy_error = type(exc).__name__
        legacy = Extraction(dict.fromkeys(vision_ocr.CORE_FIELDS), {},
                            {'engine': 'legacy-error', 'error_type': legacy_error}, True)
    legacy.raw['image_sha256'] = hashlib.sha256(image_bytes).hexdigest()
    legacy.raw['vision'] = dict(config)
    if config['status'] != 'CONFIGURED':
        if config['mode'] != 'off':
            legacy.review_required = True
        return legacy
    try:
        vision_started = time.perf_counter()
        result = vision_ocr.read_invoice(image_bytes,
            api_key=os.environ.get('GEMINI_API_KEY', ''), model=config['model'])
        legacy.raw.setdefault("timings_ms", {})["vision_ms"] = round((time.perf_counter() - vision_started) * 1000, 1)
        fields, issues = vision_ocr.validated_fields(result['payload'])
        uncertain = set(result['payload'].get('uncertain_fields') or [])
        field_trace = {}
        for key in vision_ocr.CORE_FIELDS:
            alias = 'seller_name' if key == 'vendor_name' else key
            candidate = result['payload'].get(alias)
            value = fields.get(key)
            is_uncertain = key in uncertain or alias in uncertain
            if candidate is None:
                trace_status, reason = 'missing', 'not_read_from_image'
            elif value is None:
                trace_status, reason = 'invalid', 'validation_rejected'
            elif is_uncertain:
                trace_status, reason = 'needs_review', 'model_marked_uncertain'
            else:
                trace_status, reason = 'extracted', None
            field_trace[key] = {
                'raw_text': candidate,
                'value': value,
                'status': trace_status,
                'source': 'image_main',
                'reason': reason,
                'evidence_region': None,
            }
    except Exception as exc:
        legacy.raw['vision']['status'] = str(exc) if isinstance(exc, vision_ocr.VisionError) else 'INVALID_RESPONSE'
        legacy.review_required = True
        return legacy
    result.update({
        'status': 'SUCCEEDED',
        'mode': config['mode'],
        'validation_issues': issues,
        'field_trace': field_trace,
    })
    comparison = {key: {'legacy': legacy.fields.get(key), 'vision': fields.get(key),
                        'equal': legacy.fields.get(key) == fields.get(key)} for key in vision_ocr.CORE_FIELDS}
    legacy.raw['vision'] = result
    legacy.raw['comparison'] = comparison
    if config['mode'] == 'shadow':
        # Disagreement must not silently pass as a successful extraction.
        legacy.review_required |= bool(issues or result['payload']['needs_review'] or
                                       any(not v['equal'] for v in comparison.values()))
        return legacy
    # Primary Vision is an enrichment layer, never a destructive whole-record replacement.
    # Preserve every usable legacy value when Vision is missing/invalid. When both disagree,
    # prefer the existing value and surface the Vision candidate for review instead of silently
    # overwriting either side.
    merged_fields = dict(legacy.fields)
    merged_confidence = dict(legacy.confidence)
    field_sources = {
        k: ('legacy' if v not in (None, '') else None)
        for k, v in merged_fields.items()
    }
    conflicts = {}
    for key in vision_ocr.CORE_FIELDS:
        vision_value = fields.get(key)
        legacy_value = merged_fields.get(key)
        if vision_value in (None, ''):
            continue
        if legacy_value in (None, ''):
            merged_fields[key] = vision_value
            field_sources[key] = 'whole_image_vision'
            continue
        if legacy_value == vision_value:
            field_sources[key] = 'legacy+whole_image_vision'
            continue
        conflicts[key] = {
            'legacy': legacy_value,
            'vision': vision_value,
            'resolution': 'preserve_legacy_pending_review',
        }
    return Extraction(merged_fields, merged_confidence, {
        'engine': 'legacy+gemini-whole-image-v1', 'image_sha256': result['image_sha256'],
        'vision': result, 'comparison': comparison, 'conflicts': conflicts,
        'legacy': {'fields': legacy.fields, 'confidence': legacy.confidence,
                   'raw': {k: v for k, v in legacy.raw.items() if k not in {'vision', 'comparison'}}},
        'field_sources': field_sources,
        'review': {
            'status': 'needs_review' if (issues or conflicts or result['payload']['needs_review']) else 'extracted',
            'required_fields': [],
            'confirm_fields': sorted(set(issues) | set(conflicts)),
            'reasons': (
                [f'vision_issue:{x}' for x in sorted(set(issues))]
                + [f'vision_conflict:{x}' for x in sorted(conflicts)]
            ),
        },
    }, bool(issues or conflicts or result['payload']['needs_review']))


class InvoiceStore:
    def __init__(self, root: Path, *, data_scope: str = "production"):
        self.root = root
        self.data_scope = data_scope
        self.originals = root / "originals"
        self.db_path = root / "invoice-intake.sqlite3"
        max_parallel = max(1, min(4, int(os.environ.get("INVOICE_OCR_PARALLELISM", "2"))))
        self.processing_slots = threading.BoundedSemaphore(max_parallel)
        self.deep_fallback_slots = threading.BoundedSemaphore(
            max(1, min(2, int(os.environ.get("INVOICE_DEEP_FALLBACK_PARALLELISM", "1"))))
        )
        stamp_db = Path(os.environ.get("STAMP_REGISTRY_PATH", str(root / "stamp-recognition.sqlite3")))
        self.stamp_store = StampStore(stamp_db)
        ocr_memory_db = Path(os.environ.get("OCR_MEMORY_PATH", str(root / "ocr-memory.sqlite3")))
        self.ocr_memory = OCRMemoryStore(ocr_memory_db)
        self.originals.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS intake_batches(
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              data_scope TEXT NOT NULL,
              status TEXT NOT NULL,
              item_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY,
              sha256 TEXT NOT NULL UNIQUE,
              original_filename TEXT NOT NULL,
              mime_type TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              stored_path TEXT NOT NULL,
              batch_id TEXT REFERENCES intake_batches(id),
              source_type TEXT NOT NULL DEFAULT 'unknown',
              data_scope TEXT NOT NULL DEFAULT 'production',
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS extractions(
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL REFERENCES documents(id),
              engine TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices(
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
              invoice_number TEXT,
              invoice_date TEXT,
              vendor_name TEXT,
              buyer_tax_id TEXT,
              seller_tax_id TEXT,
              amount_before_tax INTEGER,
              tax_amount INTEGER,
              total_amount INTEGER,
              status TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_line_items(
              id TEXT PRIMARY KEY,
              invoice_id TEXT NOT NULL REFERENCES invoices(id),
              line_no INTEGER NOT NULL,
              description TEXT,
              quantity TEXT,
              unit_price INTEGER,
              amount INTEGER,
              source TEXT NOT NULL,
              confidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(invoice_id,line_no)
            );
            CREATE TABLE IF NOT EXISTS reviews(
              id TEXT PRIMARY KEY,
              invoice_id TEXT NOT NULL REFERENCES invoices(id),
              actor TEXT NOT NULL,
              before_json TEXT NOT NULL,
              after_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_invoice_line_items_invoice ON invoice_line_items(invoice_id,line_no);
            """)
            invoice_columns = {row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "buyer_tax_id" not in invoice_columns:
                db.execute("ALTER TABLE invoices ADD COLUMN buyer_tax_id TEXT")
            if "deleted_at" not in invoice_columns:
                db.execute("ALTER TABLE invoices ADD COLUMN deleted_at TEXT")
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "batch_id" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN batch_id TEXT REFERENCES intake_batches(id)")
            if "source_type" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_type TEXT NOT NULL DEFAULT 'unknown'")
            if "data_scope" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN data_scope TEXT NOT NULL DEFAULT 'production'")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_batch ON documents(batch_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_scope_source ON documents(data_scope, source_type)")

    def ingest(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        *,
        source_type: str = "unknown",
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist immutable original and provisional DB row quickly.

        OCR intentionally runs later so continuous scanning is not blocked
        by Tesseract latency.
        """
        source_type = source_type if source_type in {"camera", "upload", "api", "unknown"} else "unknown"
        batch_id = batch_id or str(uuid.uuid4())
        sha = hashlib.sha256(image_bytes).hexdigest()
        with self.connect() as db:
            found = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.id AS matched_document_id,
                     d.batch_id, d.source_type, d.data_scope
              FROM documents d LEFT JOIN invoices i ON i.document_id=d.id
              WHERE d.sha256=?
            """, (sha,)).fetchone()
            if found:
                if "deleted_at" in found.keys() and found["deleted_at"]:
                    restored_at = utcnow()
                    db.execute(
                        """UPDATE invoices SET
                             deleted_at=NULL,
                             status='processing',
                             confidence_json='{}',
                             updated_at=?
                           WHERE id=?""",
                        (restored_at, found["id"]),
                    )
                    db.execute(
                        """INSERT OR IGNORE INTO intake_batches(
                             id,source_type,data_scope,status,item_count,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?)""",
                        (batch_id, source_type, self.data_scope, "open", 0, restored_at, restored_at),
                    )
                    db.execute(
                        """UPDATE documents SET batch_id=?, source_type=?, data_scope=?
                           WHERE id=?""",
                        (batch_id, source_type, self.data_scope, found["matched_document_id"]),
                    )
                    db.execute(
                        "UPDATE intake_batches SET item_count=item_count+1, updated_at=? WHERE id=?",
                        (restored_at, batch_id),
                    )
                    restored = db.execute("""
                      SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope
                      FROM invoices i JOIN documents d ON d.id=i.document_id
                      WHERE i.id=?
                    """, (found["id"],)).fetchone()
                    payload = self._row_payload(restored, duplicate=False)
                    payload["restored"] = True
                    return payload
                return self._row_payload(found, duplicate=True)

        ext = ".jpg"
        if mime_type == "image/png":
            ext = ".png"
        elif mime_type == "image/webp":
            ext = ".webp"

        now = datetime.now(timezone.utc)
        rel_dir = Path(f"{now.year:04d}") / f"{now.month:02d}"
        target_dir = self.originals / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        document_id = str(uuid.uuid4())
        invoice_id = str(uuid.uuid4())
        created = utcnow()
        target = target_dir / f"{document_id}{ext}"

        with target.open("xb") as fh:
            fh.write(image_bytes)

        with self.connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO intake_batches(
                     id,source_type,data_scope,status,item_count,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (batch_id, source_type, self.data_scope, "open", 0, created, created),
            )
            db.execute(
                """INSERT INTO documents(
                     id,sha256,original_filename,mime_type,size_bytes,stored_path,
                     batch_id,source_type,data_scope,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id, sha, filename, mime_type, len(image_bytes), str(target),
                    batch_id, source_type, self.data_scope, created,
                ),
            )
            db.execute(
                "UPDATE intake_batches SET item_count=item_count+1, updated_at=? WHERE id=?",
                (created, batch_id),
            )
            db.execute("""
              INSERT INTO invoices(
                id,document_id,invoice_number,invoice_date,vendor_name,seller_tax_id,
                amount_before_tax,tax_amount,total_amount,status,confidence_json,created_at,updated_at
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                invoice_id, document_id, None, None, None, None,
                None, None, None, "processing", "{}", created, created
            ))

        return {
            "ok": True,
            "duplicate": False,
            "archived": True,
            "document_id": document_id,
            "invoice_id": invoice_id,
            "status": "processing",
            "fields": {
                "invoice_number": None,
                "invoice_date": None,
                "vendor_name": None,
                "buyer_tax_id": None,
                "seller_tax_id": None,
                "amount_before_tax": None,
                "tax_amount": None,
                "total_amount": None,
            },
            "confidence": {},
            "engine": "tesseract-layout-v2-async",
            "sha256": sha,
            "original_filename": filename,
            "batch_id": batch_id,
            "source_type": source_type,
            "data_scope": self.data_scope,
        }

    def process(self, invoice_id: str) -> dict[str, Any]:
        """Run OCR for one archived invoice and update its DB row."""
        with self.processing_slots:
            with self.connect() as db:
                row = db.execute("""
                  SELECT i.*, d.stored_path, d.sha256, d.original_filename
                  FROM invoices i JOIN documents d ON d.id=i.document_id
                  WHERE i.id=? AND i.deleted_at IS NULL
                """, (invoice_id,)).fetchone()
                if not row:
                    raise KeyError(invoice_id)
                if row["status"] != "processing":
                    return self._row_payload(row)
                image_path = Path(row["stored_path"])

            try:
                image_bytes = image_path.read_bytes()
                extraction = extract_invoice(
                    image_bytes,
                    stamp_store=self.stamp_store,
                    ocr_memory=self.ocr_memory,
                )
                extraction_id = str(uuid.uuid4())
                updated = utcnow()
                review = extraction.raw.get("review") or {}
                status = str(review.get("status") or ("needs_review" if extraction.review_required else "extracted"))
                deep_pending = status in {"recognition_insufficient", "needs_review"}
                extraction.raw["deep_fallback_pending"] = deep_pending
                f = extraction.fields

                with self.connect() as db:
                    db.execute(
                        "INSERT INTO extractions VALUES(?,?,?,?,?)",
                        (
                            extraction_id,
                            row["document_id"],
                            extraction.raw["engine"],
                            json.dumps(extraction.raw, ensure_ascii=False),
                            updated,
                        ),
                    )
                    db.execute("DELETE FROM invoice_line_items WHERE invoice_id=?", (invoice_id,))
                    vision_payload = ((extraction.raw.get("vision") or {}).get("payload") or {})
                    line_items = vision_payload.get("line_items") or extraction.raw.get("line_items") or []
                    for idx, item in enumerate(line_items, start=1):
                        db.execute(
                            """INSERT INTO invoice_line_items(
                                 id,invoice_id,line_no,description,quantity,unit_price,amount,
                                 source,confidence_json,created_at,updated_at
                               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                str(uuid.uuid4()), invoice_id, idx,
                                item.get("description"),
                                None if item.get("quantity") is None else str(item.get("quantity")),
                                item.get("unit_price"),
                                item.get("amount"),
                                "whole_image_vision" if vision_payload else "ocr",
                                "{}",
                                updated, updated,
                            ),
                        )
                    db.execute("""
                      UPDATE invoices SET
                        invoice_number=?, invoice_date=?, vendor_name=?, buyer_tax_id=?, seller_tax_id=?,
                        amount_before_tax=?, tax_amount=?, total_amount=?, status=?,
                        confidence_json=?, updated_at=?
                      WHERE id=?
                    """, (
                        f["invoice_number"], f["invoice_date"], f["vendor_name"], f.get("buyer_tax_id"), f["seller_tax_id"],
                        f["amount_before_tax"], f["tax_amount"], f["total_amount"], status,
                        json.dumps(extraction.confidence, ensure_ascii=False), updated, invoice_id,
                    ))
                    done = db.execute("""
                      SELECT i.*, d.sha256, d.original_filename,
                             ? AS extraction_payload
                      FROM invoices i JOIN documents d ON d.id=i.document_id
                      WHERE i.id=?
                    """, (json.dumps(extraction.raw, ensure_ascii=False), invoice_id)).fetchone()
                    payload = self._row_payload(done)
                    payload["engine"] = extraction.raw["engine"]
                    # Fast OCR is already terminal for the user-visible recognition flow.
                    # Background enrichment must never keep the UI in "recognizing".
                    payload["background_enrichment_pending"] = deep_pending
                    payload["deep_fallback_pending"] = False

                if deep_pending:
                    threading.Thread(
                        target=self._deep_enrich_invoice,
                        args=(invoice_id,),
                        name=f"invoice-deep-{invoice_id[:8]}",
                        daemon=True,
                    ).start()
                return payload
            except Exception as exc:
                failed_at = utcnow()
                error_type = type(exc).__name__
                error_payload = {
                    "engine": "invoice-processing-error",
                    "status": "error",
                    "error": {
                        "stage": "process",
                        "type": error_type,
                        "reason": str(exc)[:240] if str(exc) else None,
                    },
                    "deep_fallback_pending": False,
                }
                try:
                    with self.connect() as db:
                        current = db.execute(
                            "SELECT document_id FROM invoices WHERE id=?",
                            (invoice_id,),
                        ).fetchone()
                        if current:
                            db.execute(
                                "INSERT INTO extractions VALUES(?,?,?,?,?)",
                                (
                                    str(uuid.uuid4()),
                                    current["document_id"],
                                    "invoice-processing-error",
                                    json.dumps(error_payload, ensure_ascii=False),
                                    failed_at,
                                ),
                            )
                        db.execute(
                            "UPDATE invoices SET status='error', updated_at=? WHERE id=?",
                            (failed_at, invoice_id),
                        )
                finally:
                    print(f"invoice_process=error type:{error_type}")
                raise

    def _deep_enrich_invoice(self, invoice_id: str) -> None:
        """Improve an already-visible fast result without blocking the user.

        Deep fallback is optional, but its state is not: once started it must
        always end in a terminal receipt so the UI cannot poll forever.
        """
        with self.deep_fallback_slots:
            row = None
            base_raw: dict[str, Any] | None = None
            original_status: str | None = None
            started = time.perf_counter()
            try:
                with self.connect() as db:
                    row = db.execute(
                        """SELECT i.*, d.stored_path, d.sha256, d.original_filename
                           FROM invoices i JOIN documents d ON d.id=i.document_id
                           WHERE i.id=? AND i.deleted_at IS NULL""",
                        (invoice_id,),
                    ).fetchone()
                    if not row or row["status"] not in {"recognition_insufficient", "needs_review"}:
                        return
                    extraction_row = db.execute(
                        """SELECT payload_json FROM extractions
                           WHERE document_id=? ORDER BY rowid DESC LIMIT 1""",
                        (row["document_id"],),
                    ).fetchone()
                    if not extraction_row:
                        return
                    base_raw = json.loads(extraction_row["payload_json"])
                    base = Extraction(
                        fields={
                            "invoice_number": row["invoice_number"],
                            "invoice_date": row["invoice_date"],
                            "vendor_name": row["vendor_name"],
                            "buyer_tax_id": row["buyer_tax_id"] if "buyer_tax_id" in row.keys() else None,
                            "seller_tax_id": row["seller_tax_id"],
                            "amount_before_tax": row["amount_before_tax"],
                            "tax_amount": row["tax_amount"],
                            "total_amount": row["total_amount"],
                        },
                        confidence=json.loads(row["confidence_json"] or "{}"),
                        raw=base_raw,
                        review_required=True,
                    )
                    image_path = Path(row["stored_path"])
                    original_status = str(row["status"])

                budget = max(
                    5.0,
                    min(120.0, float(os.environ.get("INVOICE_DEEP_FALLBACK_BUDGET_SECONDS", "60"))),
                )
                enriched = deep_fallback_enrich(
                    image_path.read_bytes(),
                    base,
                    budget_seconds=budget,
                )
                enriched.raw["deep_fallback_pending"] = False
                review = enriched.raw.get("review") or {}
                new_status = str(review.get("status") or original_status)
                updated = utcnow()
                fields = enriched.fields

                with self.connect() as db:
                    current = db.execute(
                        "SELECT status FROM invoices WHERE id=? AND deleted_at IS NULL",
                        (invoice_id,),
                    ).fetchone()
                    if not current or current["status"] != original_status:
                        return
                    db.execute(
                        "INSERT INTO extractions VALUES(?,?,?,?,?)",
                        (
                            str(uuid.uuid4()),
                            row["document_id"],
                            enriched.raw["engine"],
                            json.dumps(enriched.raw, ensure_ascii=False),
                            updated,
                        ),
                    )
                    db.execute(
                        """UPDATE invoices SET
                             invoice_number=?, invoice_date=?, vendor_name=?, buyer_tax_id=?, seller_tax_id=?,
                             amount_before_tax=?, tax_amount=?, total_amount=?, status=?,
                             confidence_json=?, updated_at=?
                           WHERE id=?""",
                        (
                            fields["invoice_number"], fields["invoice_date"],
                            fields["vendor_name"], fields.get("buyer_tax_id"), fields["seller_tax_id"],
                            fields["amount_before_tax"], fields["tax_amount"],
                            fields["total_amount"], new_status,
                            json.dumps(enriched.confidence, ensure_ascii=False),
                            updated, invoice_id,
                        ),
                    )
                print(
                    "invoice_deep_fallback="
                    f"completed status:{new_status} "
                    f"elapsed_ms:{round((time.perf_counter()-started)*1000,1)}"
                )
            except Exception as exc:
                # Keep the fast result, but explicitly terminate background state.
                if row is not None and base_raw is not None and original_status is not None:
                    failed_raw = json.loads(json.dumps(base_raw, ensure_ascii=False))
                    failed_raw["deep_fallback_pending"] = False
                    failed_raw["deep_fallback"] = {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                    failed_raw.setdefault("timings_ms", {})["deep_fallback_ms"] = (
                        failed_raw["deep_fallback"]["elapsed_ms"]
                    )
                    try:
                        with self.connect() as db:
                            current = db.execute(
                                "SELECT status FROM invoices WHERE id=? AND deleted_at IS NULL",
                                (invoice_id,),
                            ).fetchone()
                            if current and current["status"] == original_status:
                                db.execute(
                                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                                    (
                                        str(uuid.uuid4()),
                                        row["document_id"],
                                        str(failed_raw.get("engine") or "deep-fallback-error"),
                                        json.dumps(failed_raw, ensure_ascii=False),
                                        utcnow(),
                                    ),
                                )
                    except Exception:
                        pass
                print(
                    "invoice_deep_fallback="
                    f"error type:{type(exc).__name__} "
                    f"elapsed_ms:{round((time.perf_counter()-started)*1000,1)}"
                )
                return

    def stale_processing_ids(self, *, limit: int = 50) -> list[str]:
        """Return old processing rows that no longer have a trustworthy in-process worker."""
        limit = max(1, min(500, limit))
        with self.connect() as db:
            rows = db.execute(
                """SELECT id,status,updated_at FROM invoices
                   WHERE status='processing' AND deleted_at IS NULL
                   ORDER BY updated_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            str(row["id"])
            for row in rows
            if processing_is_stale(row["status"], row["updated_at"])
        ]

    def recover_stale_processing(self, *, limit: int = 50) -> dict[str, Any]:
        """Resume stale OCR work from immutable originals after a service restart."""
        ids = self.stale_processing_ids(limit=limit)
        recovered: list[str] = []
        failed: list[str] = []
        for invoice_id in ids:
            try:
                self.process(invoice_id)
                recovered.append(invoice_id)
            except Exception:
                failed.append(invoice_id)
        return {
            "attempted": len(ids),
            "recovered": recovered,
            "failed": failed,
        }

    def reprocess(self, invoice_id: str) -> dict[str, Any]:
        """Re-run OCR for an existing immutable original without creating a new record."""
        with self.connect() as db:
            row = db.execute("SELECT id FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            db.execute(
                "UPDATE invoices SET status='processing', updated_at=? WHERE id=?",
                (utcnow(), invoice_id),
            )
        return self.process(invoice_id)

    def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope,
                     (SELECT e.engine FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_engine,
                     (SELECT e.payload_json FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_payload
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.id=? AND i.deleted_at IS NULL
            """, (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            payload = self._row_payload(row)
            extraction = db.execute(
                "SELECT payload_json FROM extractions WHERE document_id=? ORDER BY rowid DESC LIMIT 1",
                (row['document_id'],),
            ).fetchone()
            payload['recognition'] = json.loads(extraction['payload_json']) if extraction else None
            items = db.execute(
                """SELECT line_no,description,quantity,unit_price,amount,source,confidence_json
                   FROM invoice_line_items WHERE invoice_id=? ORDER BY line_no""",
                (invoice_id,),
            ).fetchall()
            payload['line_items'] = [dict(item) for item in items]
            return payload

    def get_original(self, invoice_id: str) -> dict[str, Any]:
        """Return validated metadata for the immutable original image."""
        with self.connect() as db:
            row = db.execute("""
              SELECT d.stored_path, d.mime_type, d.original_filename, d.sha256
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.id=?
            """, (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)

        path = Path(row["stored_path"]).resolve()
        originals_root = self.originals.resolve()
        try:
            path.relative_to(originals_root)
        except ValueError as exc:
            raise ValueError("original_path_outside_store") from exc
        if not path.is_file():
            raise FileNotFoundError(invoice_id)

        return {
            "path": path,
            "mime_type": row["mime_type"],
            "original_filename": row["original_filename"],
            "sha256": row["sha256"],
        }

    def _row_payload(self, row: sqlite3.Row, duplicate: bool = False) -> dict[str, Any]:
        return {
            "ok": True,
            "duplicate": duplicate,
            "archived": True,
            "document_id": row["document_id"] if "document_id" in row.keys() else None,
            "invoice_id": row["id"] if "id" in row.keys() else None,
            "status": row["status"] if "status" in row.keys() else "archived",
            "fields": {
                "invoice_number": row["invoice_number"] if "invoice_number" in row.keys() else None,
                "invoice_date": row["invoice_date"] if "invoice_date" in row.keys() else None,
                "vendor_name": row["vendor_name"] if "vendor_name" in row.keys() else None,
                "buyer_tax_id": row["buyer_tax_id"] if "buyer_tax_id" in row.keys() else None,
                "seller_tax_id": row["seller_tax_id"] if "seller_tax_id" in row.keys() else None,
                "amount_before_tax": row["amount_before_tax"] if "amount_before_tax" in row.keys() else None,
                "tax_amount": row["tax_amount"] if "tax_amount" in row.keys() else None,
                "total_amount": row["total_amount"] if "total_amount" in row.keys() else None,
            },
            "confidence": json.loads(row["confidence_json"]) if "confidence_json" in row.keys() and row["confidence_json"] else {},
            "engine": row["extraction_engine"] if "extraction_engine" in row.keys() and row["extraction_engine"] else None,
            "sha256": row["sha256"] if "sha256" in row.keys() else None,
            "original_filename": row["original_filename"] if "original_filename" in row.keys() else None,
            "batch_id": row["batch_id"] if "batch_id" in row.keys() else None,
            "source_type": row["source_type"] if "source_type" in row.keys() else None,
            "data_scope": row["data_scope"] if "data_scope" in row.keys() else None,
            "updated_at": row["updated_at"] if "updated_at" in row.keys() else None,
            "processing_stale": processing_is_stale(
                row["status"] if "status" in row.keys() else None,
                row["updated_at"] if "updated_at" in row.keys() else None,
            ),
            "review": (
                (json.loads(row["extraction_payload"]).get("review") or {})
                if "extraction_payload" in row.keys() and row["extraction_payload"]
                else {}
            ),
            # Compatibility field: user-visible recognition is terminal once fast OCR
            # has left status=processing. Deep OCR is optional background enrichment.
            "deep_fallback_pending": False,
            "background_enrichment_pending": (
                bool(json.loads(row["extraction_payload"]).get("deep_fallback_pending"))
                if "extraction_payload" in row.keys() and row["extraction_payload"]
                else False
            ),
        }

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(100, limit))
        with self.connect() as db:
            rows = db.execute("""
              SELECT i.*, d.sha256, d.original_filename, d.batch_id, d.source_type, d.data_scope,
                     (SELECT e.engine FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_engine,
                     (SELECT e.payload_json FROM extractions e WHERE e.document_id=i.document_id
                      ORDER BY e.rowid DESC LIMIT 1) AS extraction_payload
              FROM invoices i JOIN documents d ON d.id=i.document_id
              WHERE i.deleted_at IS NULL
              ORDER BY i.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_payload(row) for row in rows]

    def hard_delete(self, invoice_id: str, actor: str) -> dict[str, Any]:
        """Permanently delete one invoice, its derived data, document row and original file."""
        with self.connect() as db:
            row = db.execute(
                """SELECT i.id AS invoice_id, i.document_id, d.stored_path, d.batch_id
                   FROM invoices i JOIN documents d ON d.id=i.document_id
                   WHERE i.id=?""",
                (invoice_id,),
            ).fetchone()
            if not row:
                raise KeyError(invoice_id)
            stored_path = Path(row["stored_path"])
            document_id = row["document_id"]
            batch_id = row["batch_id"]

            db.execute("DELETE FROM reviews WHERE invoice_id=?", (invoice_id,))
            db.execute("DELETE FROM invoice_line_items WHERE invoice_id=?", (invoice_id,))
            db.execute("DELETE FROM extractions WHERE document_id=?", (document_id,))
            db.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
            if batch_id:
                db.execute(
                    """UPDATE intake_batches
                       SET item_count=CASE WHEN item_count>0 THEN item_count-1 ELSE 0 END,
                           updated_at=?
                       WHERE id=?""",
                    (utcnow(), batch_id),
                )

        try:
            stored_path.unlink(missing_ok=True)
        except OSError:
            # DB deletion is authoritative; orphan cleanup can be handled separately.
            pass
        return {"ok": True, "invoice_id": invoice_id, "permanent": True}

    def hard_delete_many(self, invoice_ids: list[str], actor: str) -> dict[str, Any]:
        deleted = []
        for invoice_id in invoice_ids:
            try:
                self.hard_delete(invoice_id, actor)
                deleted.append(invoice_id)
            except KeyError:
                continue
        return {"ok": True, "deleted": deleted, "count": len(deleted), "permanent": True}

    def soft_delete(self, invoice_id: str, actor: str) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as db:
            row = db.execute(
                "SELECT id,deleted_at FROM invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            if not row:
                raise KeyError(invoice_id)
            if row["deleted_at"] is None:
                db.execute(
                    "UPDATE invoices SET deleted_at=?, updated_at=? WHERE id=?",
                    (now, now, invoice_id),
                )
                db.execute(
                    "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), invoice_id, actor,
                        json.dumps({"deleted_at": None}, ensure_ascii=False),
                        json.dumps({"deleted_at": now}, ensure_ascii=False),
                        now,
                    ),
                )
        return {"ok": True, "invoice_id": invoice_id, "deleted_at": now}

    def soft_delete_many(self, invoice_ids: list[str], actor: str) -> dict[str, Any]:
        deleted = []
        for invoice_id in invoice_ids:
            try:
                self.soft_delete(invoice_id, actor)
                deleted.append(invoice_id)
            except KeyError:
                continue
        return {"ok": True, "deleted": deleted, "count": len(deleted)}

    def review(self, invoice_id: str, actor: str, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {"invoice_number", "invoice_date", "vendor_name", "buyer_tax_id", "seller_tax_id", "amount_before_tax", "tax_amount", "total_amount"}
        cleaned = {k: fields.get(k) for k in allowed if k in fields}
        with self.connect() as db:
            row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not row:
                raise KeyError(invoice_id)
            before = dict(row)
            extraction_row = db.execute(
                "SELECT payload_json FROM extractions WHERE document_id=? ORDER BY rowid DESC LIMIT 1",
                (row["document_id"],),
            ).fetchone()
            extraction_raw = json.loads(extraction_row["payload_json"]) if extraction_row else {}
            current = {k: before.get(k) for k in allowed}
            current.update(cleaned)
            if current.get("amount_before_tax") is not None and current.get("tax_amount") is not None and current.get("total_amount") is not None:
                if int(current["amount_before_tax"]) + int(current["tax_amount"]) != int(current["total_amount"]):
                    raise ValueError("amount_validation_failed")
            if current.get("invoice_number") and not re.fullmatch(r"[A-Z]{2}\d{8}", str(current["invoice_number"]).upper()):
                raise ValueError("invoice_number_validation_failed")
            now = utcnow()
            assignments = ",".join(f"{k}=?" for k in cleaned)
            values = list(cleaned.values())
            if assignments:
                db.execute(f"UPDATE invoices SET {assignments}, status='reviewed', updated_at=? WHERE id=?", (*values, now, invoice_id))
            else:
                db.execute("UPDATE invoices SET status='reviewed', updated_at=? WHERE id=?", (now, invoice_id))
            after = db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), invoice_id, actor, json.dumps(before, ensure_ascii=False), json.dumps(dict(after), ensure_ascii=False), now),
            )
            doc = db.execute("SELECT sha256,original_filename,stored_path FROM documents WHERE id=?", (after["document_id"],)).fetchone()
            merged = dict(after)
            merged["sha256"] = doc["sha256"]
            merged["original_filename"] = doc["original_filename"]

        # Learn only explicit human corrections. A blank OCR observation is not
        # promoted into an automatic rule because there is no repeatable error token.
        try:
            memory_context = context_from_extraction(extraction_raw, current)
            for key in allowed:
                observed = before.get(key)
                corrected = current.get(key)
                if observed not in (None, "") and corrected != observed:
                    self.ocr_memory.remember(
                        field_name=key,
                        observed_value=observed,
                        corrected_value=corrected,
                        context=memory_context,
                        actor=actor,
                    )
        except (ValueError, TypeError, sqlite3.Error):
            # Review remains authoritative even if optional learning fails.
            pass

        # Human review confirms business attributes. For an unknown visual stamp,
        # enroll the cropped fingerprint as a new physical stamp. A near/uncertain
        # visual match is deliberately not auto-enrolled as either old or new.
        try:
            image_bytes = Path(doc["stored_path"]).read_bytes()
            regions = detect_stamp_regions(image_bytes)
            if regions and current.get("vendor_name") and current.get("seller_tax_id"):
                fp = fingerprint_stamp(image_bytes, regions[0])
                match = self.stamp_store.match(fp)
                if match.decision == "unknown_stamp":
                    self.stamp_store.learn_confirmed(
                        fp,
                        entity_id=str(current.get("seller_tax_id")),
                        canonical_label=str(current.get("vendor_name")),
                        verified_attributes={
                            "vendor_name": current.get("vendor_name"),
                            "seller_tax_id": current.get("seller_tax_id"),
                        },
                    )
                elif match.decision == "same_stamp" and match.stamp_id:
                    self.stamp_store.learn_confirmed(
                        fp,
                        stamp_id=match.stamp_id,
                        entity_id=match.entity_id,
                        canonical_label=str(current.get("vendor_name")),
                        verified_attributes={
                            "vendor_name": current.get("vendor_name"),
                            "seller_tax_id": current.get("seller_tax_id"),
                        },
                    )
        except (OSError, ValueError, sqlite3.Error):
            # Review must remain authoritative even if optional stamp learning fails.
            pass
        return self._row_payload(sqlite3.Row if False else _DictRow(merged))


class _DictRow(dict):
    def keys(self):
        return super().keys()
