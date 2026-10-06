from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from rapidocr import RapidOCR

INV_RE = re.compile(r"([A-Z]{2})\s*[- ]?\s*(\d{8})")


def _ocr_evidence(result) -> tuple[list[dict[str, Any]], str, float]:
    """Preserve token text, confidence and geometry instead of flattening OCR immediately."""
    txts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    if hasattr(result, "txts") and result.txts is not None:
        txts = [str(x) for x in result.txts]
        raw_scores = getattr(result, "scores", None)
        if raw_scores is not None:
            scores = [float(x) for x in raw_scores]
        raw_boxes = getattr(result, "boxes", None)
        if raw_boxes is not None:
            boxes = list(raw_boxes)
    elif hasattr(result, "to_json"):
        obj = result.to_json()
        if isinstance(obj, str):
            import json
            obj = json.loads(obj)
        obj = obj or {}
        txts = [str(x) for x in (obj.get("txts") or obj.get("texts") or obj.get("rec_texts") or [])]
        scores = [float(x) for x in (obj.get("scores") or obj.get("rec_scores") or [])]
        boxes = list(obj.get("boxes") or obj.get("dt_polys") or [])

    evidence: list[dict[str, Any]] = []
    for idx, text in enumerate(txts):
        score = scores[idx] if idx < len(scores) else None
        box = boxes[idx] if idx < len(boxes) else None
        if hasattr(box, "tolist"):
            box = box.tolist()
        evidence.append({
            "index": idx,
            "text": text,
            "confidence": score,
            "box": box,
        })
    text = "\n".join(txts)
    confidence = sum(scores) / len(scores) if scores else (0.5 if text.strip() else 0.0)
    return evidence, text, round(confidence, 4)


def _texts(result) -> tuple[str, float]:
    _, text, confidence = _ocr_evidence(result)
    return text, confidence


def ocr_page(engine: RapidOCR, image_bytes: bytes) -> tuple[str, float]:
    return _texts(engine(image_bytes))


def ocr_page_evidence(engine: RapidOCR, image_bytes: bytes) -> tuple[list[dict[str, Any]], str, float]:
    return _ocr_evidence(engine(image_bytes))



def _box_bounds(box: Any) -> tuple[float, float, float, float] | None:
    if not box:
        return None
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
    except Exception:
        return None
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _norm_label(text: str) -> str:
    return (
        re.sub(r"\s+", "", text or "")
        .replace("销", "銷")
        .replace("售额", "售額")
        .replace("营业税", "營業稅")
        .replace("总计", "總計")
        .replace("合计", "合計")
    )


def layout_amount_candidates(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Rank numeric OCR tokens by geometric relation to amount labels.

    This never derives or invents an amount. It only associates already-recognized
    numeric evidence with subtotal/tax/total labels using the OCR boxes.
    """
    label_groups = {
        "amount_before_tax": ("銷售額合計", "銷售額", "合計"),
        "tax_amount": ("營業稅", "稅額"),
        "total_amount": ("總計",),
    }
    anchors: dict[str, list[tuple[dict[str, Any], tuple[float, float, float, float]]]] = {
        key: [] for key in label_groups
    }
    numeric: list[tuple[dict[str, Any], tuple[float, float, float, float], int]] = []

    for token in evidence:
        bounds = _box_bounds(token.get("box"))
        if not bounds:
            continue
        label = _norm_label(str(token.get("text") or ""))
        for field, names in label_groups.items():
            if any(name in label for name in names):
                anchors[field].append((token, bounds))
        value = _amount_token(str(token.get("text") or ""))
        if value is not None and 0 <= value <= 50_000_000:
            numeric.append((token, bounds, value))

    out: dict[str, list[dict[str, Any]]] = {key: [] for key in label_groups}
    for field, field_anchors in anchors.items():
        ranked: list[dict[str, Any]] = []
        for anchor_token, (ax1, ay1, ax2, ay2) in field_anchors:
            ah = max(1.0, ay2 - ay1)
            acy = (ay1 + ay2) / 2.0
            for token, (x1, y1, x2, y2), value in numeric:
                if token is anchor_token:
                    continue
                cy = (y1 + y2) / 2.0
                vertical = abs(cy - acy) / ah
                horizontal_gap = x1 - ax2
                # Typical invoice summary has the number to the right of the
                # label on the same row. Allow a small overlap because OCR boxes
                # can be noisy, but reject distant rows.
                if vertical > 1.6 or horizontal_gap < -ah:
                    continue
                score = max(0.0, 1.0 - min(vertical / 1.6, 1.0))
                if horizontal_gap >= 0:
                    score += 0.4
                conf = token.get("confidence")
                if isinstance(conf, (int, float)):
                    score += max(0.0, min(float(conf), 1.0)) * 0.3
                ranked.append({
                    "value": value,
                    "score": round(score, 4),
                    "text": token.get("text"),
                    "confidence": conf,
                    "box": token.get("box"),
                    "anchor": anchor_token.get("text"),
                })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        dedup: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in ranked:
            if item["value"] in seen:
                continue
            seen.add(item["value"])
            dedup.append(item)
        out[field] = dedup[:5]
    return out


def choose_layout_amounts(evidence: list[dict[str, Any]]) -> tuple[dict[str, int | None], dict[str, Any]]:
    """Choose only geometrically-supported OCR amounts; arithmetic validates, never invents."""
    candidates = layout_amount_candidates(evidence)
    chosen: dict[str, int | None] = {
        "amount_before_tax": None,
        "tax_amount": None,
        "total_amount": None,
    }
    evidence_used: dict[str, Any] = {}

    # Prefer a complete triple that is independently present in OCR and
    # arithmetically consistent. This is selection, not derivation.
    for subtotal in candidates["amount_before_tax"][:4]:
        for tax in candidates["tax_amount"][:4]:
            for total in candidates["total_amount"][:4]:
                if subtotal["value"] + tax["value"] != total["value"]:
                    continue
                chosen.update({
                    "amount_before_tax": subtotal["value"],
                    "tax_amount": tax["value"],
                    "total_amount": total["value"],
                })
                evidence_used = {
                    "amount_before_tax": subtotal,
                    "tax_amount": tax,
                    "total_amount": total,
                    "validation": "subtotal_plus_tax_equals_total",
                }
                return chosen, evidence_used

    # A high-scoring total next to an explicit total label is safe to retain
    # independently even when the other two values were not recognized.
    if candidates["total_amount"]:
        top = candidates["total_amount"][0]
        if top["score"] >= 0.9:
            chosen["total_amount"] = top["value"]
            evidence_used["total_amount"] = top

    return chosen, evidence_used



def _image_bytes(image: Image.Image, *, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


def anchor_row_reocr(
    engine: "RapidOCR",
    image_bytes: bytes,
    evidence: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Re-OCR only the numeric row beside explicit amount labels.

    This is a local recovery layer for handwriting/detection misses. It does not
    infer values from arithmetic and does not inspect unrelated page regions.
    """
    labels = {
        "amount_before_tax": ("銷售額合計", "銷售額", "合計"),
        "tax_amount": ("營業稅", "稅額"),
        "total_amount": ("總計",),
    }
    anchors: dict[str, list[tuple[float, float, float, float]]] = {
        key: [] for key in labels
    }
    for token in evidence:
        bounds = _box_bounds(token.get("box"))
        if not bounds:
            continue
        label = _norm_label(str(token.get("text") or ""))
        for field, names in labels.items():
            if any(name in label for name in names):
                anchors[field].append(bounds)

    out: dict[str, list[dict[str, Any]]] = {key: [] for key in labels}
    if not any(anchors.values()):
        return out

    try:
        with Image.open(io.BytesIO(image_bytes)) as src:
            page = ImageOps.exif_transpose(src).convert("RGB")
            width, height = page.size
            for field, boxes in anchors.items():
                candidates: list[dict[str, Any]] = []
                for ax1, ay1, ax2, ay2 in boxes:
                    ah = max(4.0, ay2 - ay1)
                    top = max(0, int(ay1 - ah * 0.9))
                    bottom = min(height, int(ay2 + ah * 0.9))
                    left = max(0, int(ax2 - ah * 0.5))
                    right = min(width, int(width * 0.99))
                    if right <= left or bottom <= top:
                        continue
                    crop = page.crop((left, top, right, bottom))
                    scale = 3
                    crop = crop.resize(
                        (max(1, crop.width * scale), max(1, crop.height * scale)),
                        Image.Resampling.LANCZOS,
                    )
                    gray = ImageOps.grayscale(crop)
                    gray = ImageOps.autocontrast(gray)
                    variants = [
                        ("autocontrast", gray),
                        ("high_contrast", ImageEnhance.Contrast(gray).enhance(1.8)),
                    ]
                    for variant_name, variant in variants:
                        result = engine(_image_bytes(variant))
                        sub_evidence, _, _ = _ocr_evidence(result)
                        for token in sub_evidence:
                            value = _amount_token(str(token.get("text") or ""))
                            if value is None or not 0 <= value <= 50_000_000:
                                continue
                            conf = token.get("confidence")
                            candidates.append({
                                "value": value,
                                "text": token.get("text"),
                                "confidence": conf,
                                "variant": variant_name,
                                "source_crop": [left, top, right, bottom],
                            })

                # Prefer candidates seen across multiple preprocess variants,
                # then OCR confidence. Repetition is evidence, not arithmetic.
                grouped: dict[int, dict[str, Any]] = {}
                for item in candidates:
                    entry = grouped.setdefault(item["value"], {
                        **item,
                        "votes": 0,
                        "best_confidence": 0.0,
                    })
                    entry["votes"] += 1
                    conf = item.get("confidence")
                    if isinstance(conf, (int, float)):
                        entry["best_confidence"] = max(entry["best_confidence"], float(conf))
                ranked = list(grouped.values())
                ranked.sort(
                    key=lambda item: (item["votes"], item["best_confidence"]),
                    reverse=True,
                )
                out[field] = ranked[:5]
    except Exception:
        return out
    return out


def choose_reocr_amounts(
    candidates: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, int | None], dict[str, Any]]:
    """Choose independently OCR-observed retry values; arithmetic only validates."""
    chosen = {
        "amount_before_tax": None,
        "tax_amount": None,
        "total_amount": None,
    }
    used: dict[str, Any] = {}

    for subtotal in candidates.get("amount_before_tax", [])[:4]:
        for tax in candidates.get("tax_amount", [])[:4]:
            for total in candidates.get("total_amount", [])[:4]:
                if subtotal["value"] + tax["value"] == total["value"]:
                    chosen.update({
                        "amount_before_tax": subtotal["value"],
                        "tax_amount": tax["value"],
                        "total_amount": total["value"],
                    })
                    used = {
                        "amount_before_tax": subtotal,
                        "tax_amount": tax,
                        "total_amount": total,
                        "validation": "subtotal_plus_tax_equals_total",
                    }
                    return chosen, used

    for field in chosen:
        items = candidates.get(field) or []
        if not items:
            continue
        top = items[0]
        # Without a complete triple, require repeated preprocess agreement or
        # very high OCR confidence before keeping an isolated value.
        if top.get("votes", 0) >= 2 or top.get("best_confidence", 0.0) >= 0.93:
            chosen[field] = top["value"]
            used[field] = top
    return chosen, used


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
    evidence, text, page_conf = ocr_page_evidence(engine, image_bytes)
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
    elif doc_type == "three_part_uniform_invoice":
        # If seller anchors were OCR'd poorly, accept a whole-page tax id only
        # when it is the sole valid candidate. Multiple ids remain ambiguous
        # because one may belong to the buyer.
        page_ids = [v for v in tax_id_candidates(text) if valid_tax_id(v)]
        page_ids = list(dict.fromkeys(page_ids))
        if len(page_ids) == 1:
            fields["seller_tax_id"] = page_ids[0]
            confidence["seller_tax_id"] = 0.86

    visual_amounts = False
    layout_values, layout_evidence = choose_layout_amounts(evidence)
    amount_sources: dict[str, str] = {}
    if doc_type == "three_part_uniform_invoice":
        subtotal, tax, total, visual_amounts = choose_three_part_amounts(text)
        fields["amount_before_tax"] = subtotal
        fields["tax_amount"] = tax
        fields["total_amount"] = total

        # Spatial evidence is a conservative fill-only layer. It recovers values
        # that the flattened-text parser missed but never overwrites an existing
        # OCR value.
        for key in ("amount_before_tax", "tax_amount", "total_amount"):
            if fields[key] is None and layout_values.get(key) is not None:
                fields[key] = layout_values[key]
                amount_sources[key] = "layout_anchor"
                confidence[key] = 0.90

        if any(fields[key] is None for key in ("amount_before_tax", "tax_amount", "total_amount")):
            retry_candidates = anchor_row_reocr(engine, image_bytes, evidence)
            retry_values, retry_evidence = choose_reocr_amounts(retry_candidates)
            for key in ("amount_before_tax", "tax_amount", "total_amount"):
                if fields[key] is None and retry_values.get(key) is not None:
                    fields[key] = retry_values[key]
                    amount_sources[key] = "anchor_row_reocr"
                    confidence[key] = 0.91

        if fields["total_amount"] is not None:
            conf = 0.97 if visual_amounts else 0.82
            if "amount_before_tax" not in amount_sources:
                confidence["amount_before_tax"] = conf if fields["amount_before_tax"] is not None else 0.0
            if "tax_amount" not in amount_sources:
                confidence["tax_amount"] = conf if fields["tax_amount"] is not None else 0.0
            if "total_amount" not in amount_sources:
                confidence["total_amount"] = conf
    else:
        retry_evidence = {}
        nums = amount_candidates(text)
        total = total_from_lines(text)
        if total is None and layout_values.get("total_amount") is not None:
            total = layout_values["total_amount"]
            amount_sources["total_amount"] = "layout_anchor"
        if total is None:
            retry_candidates = anchor_row_reocr(engine, image_bytes, evidence)
            retry_values, retry_evidence = choose_reocr_amounts(retry_candidates)
            if retry_values.get("total_amount") is not None:
                total = retry_values["total_amount"]
                amount_sources["total_amount"] = "anchor_row_reocr"
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
            confidence["total_amount"] = 0.90 if amount_sources.get("total_amount") == "layout_anchor" else 0.94

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
        "amount_sources": amount_sources,
        "layout_amount_evidence": layout_evidence,
        "reocr_amount_evidence": retry_evidence,
    }
