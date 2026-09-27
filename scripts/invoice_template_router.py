#!/usr/bin/env python3
from __future__ import annotations
import argparse, io, json, re, urllib.request
from pathlib import Path
from typing import Any
from PIL import Image, ImageEnhance, ImageOps
from rapidocr import RapidOCR

INV_RE = re.compile(r"([A-Z]{2})\s*[- ]?\s*(\d{8})")
DIGIT8_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
MONEY_RE = re.compile(r"(?<!\d)(\d{1,9})(?!\d)")
DATE_RE = re.compile(r"(?:(\d{2,4})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?")

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 invoice-template-router/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(12*1024*1024+1)
    if not data or len(data) > 12*1024*1024:
        raise RuntimeError("invalid_image")
    return data

def unpack(result) -> tuple[list[str], list[float]]:
    texts, scores = [], []
    if hasattr(result, "txts") and result.txts is not None:
        texts = [str(x) for x in result.txts]
        raw = getattr(result, "scores", None)
        if raw is not None:
            scores = [float(x) for x in raw]
    elif hasattr(result, "to_json"):
        obj = result.to_json()
        if isinstance(obj, str): obj = json.loads(obj)
        texts = [str(x) for x in (obj.get("txts") or obj.get("texts") or obj.get("rec_texts") or [])]
        scores = [float(x) for x in (obj.get("scores") or obj.get("rec_scores") or [])]
    return texts, scores

def _run_ocr(engine: RapidOCR, image: Image.Image) -> tuple[str, float]:
    buf = io.BytesIO(); image.save(buf, format="PNG")
    texts, scores = unpack(engine(buf.getvalue()))
    text = "\n".join(texts)
    score = sum(scores)/len(scores) if scores else (0.5 if text.strip() else 0.0)
    return text, score

def ocr_text(engine: RapidOCR, image: Image.Image) -> tuple[str, float]:
    # Fast path first. Only spend extra OCR passes when the first result is weak.
    base = image.convert("RGB")
    best_text, best_score = _run_ocr(engine, base)
    compact_len = len(re.sub(r"\s", "", best_text))
    if best_score >= 0.78 and compact_len >= 4:
        return best_text, round(best_score, 4)

    variants = [
        ImageOps.autocontrast(image.convert("L")).convert("RGB"),
        ImageEnhance.Contrast(ImageOps.autocontrast(image.convert("L"))).enhance(1.8).convert("RGB"),
    ]
    for variant in variants:
        text, score = _run_ocr(engine, variant)
        if len(re.sub(r"\s", "", text)) > len(re.sub(r"\s", "", best_text)) or score > best_score + 0.12:
            best_text, best_score = text, score
        if best_score >= 0.82 and len(re.sub(r"\s", "", best_text)) >= 4:
            break
    return best_text, round(best_score, 4)

def classify(text: str, templates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    compact = re.sub(r"\s+", "", text)
    best, best_score = None, 0.0
    for t in templates:
        positives = [a for a in t.get("anchors_any", []) if a in compact]
        negatives = [a for a in t.get("anchors_not", []) if a in compact]
        groups = t.get("anchors_required_groups", [])
        group_hits = sum(1 for g in groups if all(a in compact for a in g))
        denom = max(1, len(t.get("anchors_any", [])) + len(groups))
        score = (len(positives) + 1.5*group_hits - 1.5*len(negatives)) / denom
        if score > best_score:
            best, best_score = t, score
    return (best, min(1.0, round(best_score, 3))) if best_score >= 0.34 else (None, round(best_score, 3))

def crop_norm(image: Image.Image, box: list[float]) -> Image.Image:
    w,h = image.size
    x1,y1,x2,y2 = box
    return image.crop((max(0,int(x1*w)), max(0,int(y1*h)), min(w,int(x2*w)), min(h,int(y2*h))))

def parse_invoice_number(text: str):
    m = INV_RE.search(text.upper().replace("O","0"))
    return (m.group(1)+m.group(2)) if m else None

def valid_tax_id(value: str) -> bool:
    if not re.fullmatch(r"\d{8}", value or ""):
        return False
    weights = (1, 2, 1, 2, 1, 2, 4, 1)
    products = [int(d) * w for d, w in zip(value, weights)]
    total = sum((x // 10) + (x % 10) for x in products)
    if total % 10 == 0:
        return True
    # Taiwan GUI special case: 7th digit is 7 and alternate carry can validate.
    if value[6] == "7":
        alt = total - ((products[6] // 10) + (products[6] % 10)) + 1
        return alt % 10 == 0
    return False

def parse_tax_id(text: str):
    vals = DIGIT8_RE.findall(re.sub(r"[^0-9]", " ", text))
    valid = [v for v in vals if valid_tax_id(v)]
    return valid[0] if valid else (vals[0] if vals else None)

def parse_money(text: str):
    vals = [int(x) for x in MONEY_RE.findall(text.replace(",",""))]
    vals = [x for x in vals if 0 <= x <= 999_999_999]
    return max(vals) if vals else None

def parse_date(text: str):
    s = text.replace(" ","")
    m = DATE_RE.search(s)
    if not m:
        digits = re.sub(r"\D", "", s)
        for n in (7,8):
            if len(digits) >= n:
                c = digits[:n]
                if n == 7:
                    y,mo,d = int(c[:3]),int(c[3:5]),int(c[5:7]); y += 1911
                else:
                    y,mo,d = int(c[:4]),int(c[4:6]),int(c[6:8])
                if 1 <= mo <= 12 and 1 <= d <= 31:
                    return f"{y:04d}-{mo:02d}-{d:02d}"
        return None
    ys, ms, ds = m.groups()
    if not ys: return None
    y,mo,d = int(ys),int(ms),int(ds)
    if y < 1911: y += 1911
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return None

def parse_field(name: str, text: str):
    if name == "invoice_number": return parse_invoice_number(text)
    if name in {"buyer_tax_id","seller_tax_id"}: return parse_tax_id(text)
    if name in {"amount_before_tax","tax_amount","total_amount"}: return parse_money(text)
    if name == "invoice_date": return parse_date(text)
    if name in {"buyer_name","items"}:
        val = " ".join(x.strip() for x in text.splitlines() if x.strip())
        return val[:300] or None
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--templates",required=True)
    ap.add_argument("--out",default="")
    args=ap.parse_args()
    manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    templates=json.loads(Path(args.templates).read_text(encoding="utf-8"))["templates"]
    engine=RapidOCR()
    rows=[]; correct=total=template_hits=0
    for case in manifest["cases"]:
        try:
            image=Image.open(io.BytesIO(fetch(case["image_url"]))).convert("RGB")
            page_text,page_conf=ocr_text(engine,image)
            template,tconf=classify(page_text,templates)
            actual={}; evidence={}
            mode="generic_fallback"
            if template:
                mode="template"
                template_hits += 1
                actual["document_type"]=template["document_type"]
                for field,box in template["regions"].items():
                    text,conf=ocr_text(engine,crop_norm(image,box))
                    value=parse_field(field,text)
                    evidence[field]={"text":text[:500],"ocr_confidence":conf,"value":value}
                    if field != "items": actual[field]=value
            else:
                actual["invoice_number"]=parse_invoice_number(page_text)
                actual["invoice_date"]=parse_date(page_text)
                actual["seller_tax_id"]=parse_tax_id(page_text)
                actual["total_amount"]=parse_money(page_text)
            checks={}
            for field,expected in case["expected"].items():
                if field not in actual: continue
                got=actual.get(field)
                ok=str(got).replace(" ","").upper()==str(expected).replace(" ","").upper()
                checks[field]={"expected":expected,"actual":got,"ok":ok}
                total += 1; correct += int(ok)
            validation = {
                "invoice_number_format": bool(re.fullmatch(r"[A-Z]{2}\d{8}", str(actual.get("invoice_number") or ""))),
                "buyer_tax_id_checksum": (valid_tax_id(str(actual["buyer_tax_id"])) if actual.get("buyer_tax_id") else None),
                "seller_tax_id_checksum": (valid_tax_id(str(actual["seller_tax_id"])) if actual.get("seller_tax_id") else None),
            }
            if all(actual.get(k) is not None for k in ("amount_before_tax","tax_amount","total_amount")):
                validation["amount_arithmetic"] = (
                    int(actual["amount_before_tax"]) + int(actual["tax_amount"]) == int(actual["total_amount"])
                )
            else:
                validation["amount_arithmetic"] = None
            row = {"id":case["id"],"mode":mode,"template_id":template["id"] if template else None,
                   "template_confidence":tconf,"page_ocr_confidence":page_conf,
                   "actual":actual,"checks":checks,"validation":validation,"evidence":evidence}
            print("case_result="+json.dumps(row,ensure_ascii=False), flush=True)
            rows.append(row)
        except Exception as exc:
            rows.append({"id":case["id"],"error":type(exc).__name__+":"+str(exc)})
    summary={"engine":"rapidocr-template-router","cases":len(rows),"template_hits":template_hits,
             "checked_fields":total,"correct_fields":correct,
             "field_exact_match":correct/total if total else 0.0,"rows":rows}
    print("template_router_summary="+json.dumps(summary,ensure_ascii=False))
    if args.out: Path(args.out).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
