from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image, ImageOps
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rapidocr import RapidOCR

INV_RE = re.compile(r"([A-Z]{2})\s*[- ]?\s*(\d{8})")


def _texts(result) -> tuple[str, float]:
    txts, scores = [], []
    if hasattr(result, "txts") and result.txts is not None:
        txts = [str(x) for x in result.txts]
        raw = getattr(result, "scores", None)
        if raw is not None:
            scores = [float(x) for x in raw]
    elif hasattr(result, "to_json"):
        obj = result.to_json()
        if isinstance(obj, str):
            import json
            obj = json.loads(obj)
        obj = obj or {}
        txts = [str(x) for x in (obj.get("txts") or obj.get("texts") or obj.get("rec_texts") or [])]
        scores = [float(x) for x in (obj.get("scores") or obj.get("rec_scores") or [])]
    text = "\n".join(txts)
    confidence = sum(scores) / len(scores) if scores else (0.5 if text.strip() else 0.0)
    return text, round(confidence, 4)


def ocr_page(engine: RapidOCR, image_bytes: bytes) -> tuple[str, float]:
    return _texts(engine(image_bytes))


def normalize_invoice_number(text: str) -> str | None:
    s = (text or "").upper().replace("O", "0")
    m = INV_RE.search(s)
    if m:
        return m.group(1) + m.group(2)
    compact = re.sub(r"[^A-Z0-9]", "", s)
    m = re.search(r"[A-Z]{2}\d{8}", compact)
    return m.group(0) if m else None


def valid_tax_id(value: str) -> bool:
    if not re.fullmatch(r"\d{8}", value or ""):
        return False
    weights = (1, 2, 1, 2, 1, 2, 4, 1)
    products = [int(d) * w for d, w in zip(value, weights)]
    total = sum((x // 10) + (x % 10) for x in products)
    if total % 10 == 0:
        return True
    if value[6] == "7":
        alt = total - ((products[6] // 10) + (products[6] % 10)) + 1
        return alt % 10 == 0
    return False


def tax_id_candidates(text: str) -> list[str]:
    flat = re.sub(r"\s+", "", text or "")
    out: list[str] = []
    for v in re.findall(r"(?<!\d)(\d{8})(?!\d)", flat):
        if v not in out:
            out.append(v)
    for run in re.findall(r"\d{8,12}", flat):
        for i in range(len(run) - 7):
            v = run[i:i+8]
            if valid_tax_id(v) and v not in out:
                out.append(v)
    return sorted(out, key=lambda v: not valid_tax_id(v))


def normalize_date(text: str) -> str | None:
    s = text or ""
    s = re.sub(r"(?:核准日期|批准日期)[:：]?.{0,24}", "", s)
    patterns = [
        r"(?:發票日期|发票日期|日期)[:：]?\s*(?:中華民國|民國)?\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})",
        r"(?:中華民國|民國)\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})",
        r"(?:日期[:：]?)?\s*民國\s*(\d{2,3})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, s)
        if not m:
            continue
        roc, month, day = map(int, m.groups())
        if 0 <= roc < 20:
            roc += 100
        year = roc + 1911
        if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _amount_token(raw: str) -> int | None:
    raw = (raw or "").strip().strip(".-")
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", raw):
        raw = re.sub(r"[,.]", "", raw)
    else:
        raw = re.sub(r"\D", "", raw)
    return int(raw) if raw else None


def amount_candidates(text: str) -> list[int]:
    out: list[int] = []
    for raw in re.findall(r"(?<!\d)(\d{1,3}(?:[,.]\d{3})+|\d{1,7})(?!\d)", text or ""):
        v = _amount_token(raw)
        if v is not None and 0 <= v <= 50_000_000:
            out.append(v)
    return out


def total_from_lines(text: str) -> int | None:
    lines = [x.strip() for x in (text or "").splitlines()]
    for i, line in enumerate(lines):
        key = re.sub(r"\s+", "", line).replace("总", "總").replace("计", "計")
        nxt = re.sub(r"\s+", "", lines[i+1]).replace("总", "總").replace("计", "計") if i+1 < len(lines) else ""
        if "總計" not in key and not (key == "總" and nxt == "計"):
            continue
        start = i + 2 if key == "總" and nxt == "計" else i + 1
        for j in range(start, min(len(lines), start + 6)):
            if re.search(r"TEL|電話", lines[j], re.I):
                continue
            vals = []
            for raw in re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d{1,7}", lines[j]):
                v = _amount_token(raw)
                if v is not None and 0 < v < 50_000_000:
                    vals.append(v)
            if vals:
                return vals[0]
    return None


def classify(text: str) -> tuple[str | None, float]:
    compact = re.sub(r"\s+", "", text or "")
    if any(x in compact for x in ("三聯式", "扣抵聯")) or (
        ("銷售額" in compact or "销售额" in compact) and ("營業稅" in compact or "营业税" in compact)
    ):
        return "three_part_uniform_invoice", 0.90
    if any(x in compact for x in ("免用統一發票", "銀貨兩訖")) or ("收據" in compact and "合計" in compact):
        return "exempt_uniform_invoice_receipt", 0.85
    if "二聯式" in compact or ("統一發票" in compact and "收執聯" in compact):
        return "two_part_uniform_invoice", 0.85
    return None, 0.0


def choose_three_part_amounts(text: str) -> tuple[int | None, int | None, int | None, bool]:
    nums = amount_candidates(text)
    uniq = list(dict.fromkeys(nums))
    triples = []
    for subtotal in uniq:
        if subtotal < 100:
            continue
        for tax in uniq:
            if tax < 0:
                continue
            total = subtotal + tax
            if total not in uniq:
                continue
            if abs(tax - round(subtotal * 0.05)) <= 1:
                score = nums.count(subtotal) + nums.count(tax) + nums.count(total)
                triples.append((score, subtotal, tax, total))
    if triples:
        triples.sort(reverse=True)
        _, subtotal, tax, total = triples[0]
        return subtotal, tax, total, True

    total = total_from_lines(text)
    if total:
        derived = []
        for subtotal in range(max(1, int(total / 1.05) - 3), int(total / 1.05) + 4):
            tax = total - subtotal
            if subtotal + round(subtotal * 0.05) == total:
                derived.append((subtotal, tax))
        if len(derived) == 1:
            subtotal, tax = derived[0]
            return subtotal, tax, total, False
    return None, None, total, False


def seller_region_text(text: str) -> str:
    """Only text after an explicit seller/stamp anchor; never the buyer header."""
    lines = (text or '').splitlines()
    for i, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        if any(anchor in compact for anchor in ('營業人蓋用', '統一發票專用章', '銷售人名稱')):
            # The company can be immediately above the stamp's inner title.
            start = i if '營業人蓋用' in compact or '銷售人名稱' in compact else max(0, i - 1)
            return '\n'.join(lines[start:])
    return ''


def extract_template_invoice(image_bytes: bytes) -> dict[str, Any]:
    from rapidocr import RapidOCR
    engine = RapidOCR()
    text, page_conf = ocr_page(engine, image_bytes)
    doc_type, template_conf = classify(text)
    # Second-stage structural probe: some handwritten 3-part samples have a badly OCR'd
    # printed title, while invoice number + 5% subtotal/tax/total remain unambiguous.
    if not doc_type and normalize_invoice_number(text):
        subtotal_probe, tax_probe, total_probe, visual_probe = choose_three_part_amounts(text)
        if visual_probe and subtotal_probe is not None and tax_probe is not None and total_probe is not None:
            doc_type, template_conf = "three_part_uniform_invoice", 0.65
    if not doc_type:
        return {"matched": False, "engine": "rapidocr-template-v1", "raw_text": text, "page_confidence": page_conf}

    fields: dict[str, Any] = {
        "invoice_number": normalize_invoice_number(text),
        "invoice_date": normalize_date(text),
        "vendor_name": None,
        "seller_tax_id": None,
        "amount_before_tax": None,
        "tax_amount": None,
        "total_amount": None,
    }
    confidence = {k: 0.0 for k in fields}

    if fields["invoice_number"]:
        confidence["invoice_number"] = min(0.99, max(0.90, page_conf))
    if fields["invoice_date"]:
        confidence["invoice_date"] = min(0.98, max(0.88, page_conf))

    seller_text = seller_region_text(text) if doc_type == "three_part_uniform_invoice" else text
    ids = [v for v in tax_id_candidates(seller_text) if valid_tax_id(v)]
    if len(ids) == 1:
        fields["seller_tax_id"] = ids[0]
        confidence["seller_tax_id"] = 0.92

    visual_amounts = False
    if doc_type == "three_part_uniform_invoice":
        subtotal, tax, total, visual_amounts = choose_three_part_amounts(text)
        fields["amount_before_tax"] = subtotal
        fields["tax_amount"] = tax
        fields["total_amount"] = total
        if total is not None:
            conf = 0.97 if visual_amounts else 0.82
            confidence["amount_before_tax"] = conf if subtotal is not None else 0.0
            confidence["tax_amount"] = conf if tax is not None else 0.0
            confidence["total_amount"] = conf
    else:
        nums = amount_candidates(text)
        total = total_from_lines(text)
        if total is None and nums:
            freq: dict[int, int] = {}
            for v in nums:
                if 0 < v < 10_000_000:
                    freq[v] = freq.get(v, 0) + 1
            repeated = [(n, v) for v, n in freq.items() if n >= 2]
            if repeated:
                repeated.sort(reverse=True)
                total = repeated[0][1]
        fields["total_amount"] = total
        if total is not None:
            confidence["total_amount"] = 0.94

    return {
        "matched": True,
        "document_type": doc_type,
        "template_confidence": template_conf,
        "engine": "rapidocr-template-v1",
        "fields": fields,
        "confidence": confidence,
        "raw_text": text,
        "page_confidence": page_conf,
        "visual_amounts": visual_amounts,
    }
