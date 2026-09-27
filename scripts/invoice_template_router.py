#!/usr/bin/env python3
from __future__ import annotations
import argparse, io, json, re, urllib.request
from pathlib import Path
from typing import Any
from PIL import Image, ImageEnhance, ImageOps
from rapidocr import RapidOCR
import cv2
import numpy as np

INV_RE = re.compile(r"([A-Z]{2})\s*[- ]?\s*(\d{8})")
DIGIT8_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
MONEY_RE = re.compile(r"(?<!\d)(\d{1,9})(?!\d)")
DATE_RE = re.compile(r"(?:(\d{2,4})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?")


def _order_points(pts: np.ndarray) -> np.ndarray:
    pts = pts.astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    return np.array([
        pts[np.argmin(s)],
        pts[np.argmin(d)],
        pts[np.argmax(s)],
        pts[np.argmax(d)],
    ], dtype="float32")

def normalize_document(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """Detect the largest quadrilateral and perspective-warp it to a flat document."""
    rgb = np.array(image.convert("RGB"))
    h, w = rgb.shape[:2]
    scale = min(1.0, 1400.0 / max(h, w))
    work = cv2.resize(rgb, (int(w*scale), int(h*scale))) if scale < 1.0 else rgb.copy()
    gray = cv2.cvtColor(work, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5,5), 0)
    edges = cv2.Canny(gray, 45, 140)
    edges = cv2.dilate(edges, np.ones((3,3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    img_area = work.shape[0] * work.shape[1]
    best = None
    best_area = 0.0
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.18:
            break
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and area > best_area:
            best = approx.reshape(4,2)
            best_area = area
    if best is None:
        return image.convert("RGB"), {"warped": False, "reason": "no_document_quad"}

    best = best / scale
    rect = _order_points(best)
    tl,tr,br,bl = rect
    width = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
    height = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
    if width < 200 or height < 200:
        return image.convert("RGB"), {"warped": False, "reason": "quad_too_small"}
    dst = np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]], dtype="float32")
    m = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(rgb, m, (width,height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Most Taiwan handwritten invoices/receipts are landscape; normalize accidental 90-degree capture.
    if warped.shape[0] > warped.shape[1] * 1.35:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        rotated = True
    else:
        rotated = False
    coverage = float(best_area / (img_area / (scale*scale))) if scale else 0.0
    return Image.fromarray(warped), {
        "warped": True,
        "rotated_90": rotated,
        "coverage": round(max(0.0, min(1.0, coverage)), 4),
        "size": [int(warped.shape[1]), int(warped.shape[0])],
    }

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
        obj = obj or {}
        texts = [str(x) for x in (obj.get("txts") or obj.get("texts") or obj.get("rec_texts") or [])]
        scores = [float(x) for x in (obj.get("scores") or obj.get("rec_scores") or [])]
    return texts, scores

def _run_ocr(engine: RapidOCR, image: Image.Image) -> tuple[str, float]:
    # Cap OCR resolution for CPU latency. ROI coordinates are normalized, so this does not affect geometry.
    w,h=image.size
    max_side=1800
    if max(w,h)>max_side:
        scale=max_side/max(w,h)
        image=image.resize((max(1,int(w*scale)),max(1,int(h*scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO(); image.save(buf, format="PNG", optimize=False)
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


def _norm_ocr_text(text: str) -> str:
    return (text or "").replace("臺","台").replace("稅","税").replace("編","编").replace("號","号")

def contextual_money(text: str, labels: list[str]) -> int | None:
    s=_norm_ocr_text(text)
    # Allow labels to be split across OCR lines/whitespace.
    flat=re.sub(r"\\s+", "", s)
    for label in labels:
        key=re.sub(r"\\s+", "", _norm_ocr_text(label))
        pos=flat.find(key)
        if pos < 0:
            continue
        tail=flat[pos+len(key):pos+len(key)+80]
        vals=[]
        for m in re.finditer(r"(?<!\\d)(\\d{1,3}(?:,\\d{3})+|\\d{1,9})(?!\\d)", tail):
            raw=m.group(1).replace(",","")
            try:
                v=int(raw)
            except ValueError:
                continue
            # Phone numbers / tax IDs are not plausible immediate money when 8+ digits.
            if len(raw) >= 8:
                continue
            vals.append(v)
        if vals:
            return vals[0]
    return None

def contextual_tax_ids(text: str) -> list[str]:
    s=_norm_ocr_text(text)
    flat=re.sub(r"\\s+", "", s)
    out=[]
    for m in re.finditer(r"(?:統一|统一)(?:編|编)(?:號|号)[:：]?(.{0,30})", flat):
        vals=re.findall(r"(?<!\\d)(\\d{8})(?!\\d)", m.group(1))
        out.extend(vals)
    # Keep valid candidates first, preserve order and uniqueness.
    all_vals=re.findall(r"(?<!\\d)(\\d{8})(?!\\d)", flat)
    for v in all_vals:
        if v not in out:
            out.append(v)
    return sorted(dict.fromkeys(out), key=lambda v: (not valid_tax_id(v), out.index(v)))

def contextual_invoice_number(text: str) -> str | None:
    s=(text or "").upper()
    # Exact token first.
    m=INV_RE.search(s)
    if m:
        return m.group(1)+m.group(2)
    # OCR often inserts punctuation/newlines between every character.
    compact=re.sub(r"[^A-Z0-9]", "", s)
    candidates=re.findall(r"[A-Z]{2}\\d{8}", compact)
    return candidates[0] if candidates else None

def contextual_date(text: str) -> str | None:
    s=_norm_ocr_text(text)
    # Strong date phrases first.
    patterns=[
        r"(?:中華民國|民國)?\\s*(\\d{2,3})\\s*年\\s*(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*日",
        r"(?:日期[:：]?)?\\s*民國\\s*(\\d{2,3})\\s*[./-]\\s*(\\d{1,2})\\s*[./-]\\s*(\\d{1,2})",
    ]
    for p in patterns:
        m=re.search(p,s)
        if m:
            roc,mo,d=map(int,m.groups())
            if 0 <= roc < 20:
                roc += 100
            y=roc+1911
            if 2000<=y<=2100 and 1<=mo<=12 and 1<=d<=31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    candidate=parse_date(s)
    if candidate:
        try:
            y=int(candidate[:4])
            if 2000<=y<=2100:
                return candidate
        except Exception:
            pass
    return None

def extract_template_fields(page_text: str, document_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
    actual={}
    evidence={}
    inv=contextual_invoice_number(page_text)
    if inv:
        actual["invoice_number"]=inv
        evidence["invoice_number"]={"source":"page_anchor","value":inv}
    dt=contextual_date(page_text)
    if dt:
        actual["invoice_date"]=dt
        evidence["invoice_date"]={"source":"page_anchor","value":dt}

    tax_ids=contextual_tax_ids(page_text)
    if tax_ids:
        # In standard 3-part forms buyer ID is normally encountered before the seller stamp ID.
        if document_type=="three_part_uniform_invoice" and len(tax_ids)>=2:
            actual["buyer_tax_id"]=tax_ids[0]
            actual["seller_tax_id"]=tax_ids[-1]
        else:
            actual["seller_tax_id"]=tax_ids[-1]
        evidence["tax_id_candidates"]={"source":"page_anchor","values":tax_ids}

    before=contextual_money(page_text,["銷售額合計","销售额合计","銷售額(A)","销售额(A)"])
    tax=contextual_money(page_text,["營業稅","营业税"])
    total=contextual_money(page_text,["總計新臺幣","总计新台币","總計","总计"])
    if before is not None: actual["amount_before_tax"]=before
    if tax is not None: actual["tax_amount"]=tax
    if total is not None: actual["total_amount"]=total

    # Prefer a tax-arithmetic-consistent triple. This filters phone/tax-id numbers
    # that OCR often places near amount labels.
    if document_type=="three_part_uniform_invoice":
        nums=[]
        for raw in re.findall(r"(?<!\\d)(\\d{1,3}(?:,\\d{3})+|\\d{1,7})(?!\\d)", page_text):
            try: v=int(raw.replace(",",""))
            except ValueError: continue
            if 0 <= v <= 50_000_000:
                nums.append(v)
        uniq=list(dict.fromkeys(nums))
        triples=[]
        for a in uniq:
            if a <= 0: continue
            for b in uniq:
                if b < 0: continue
                t=a+b
                if t not in uniq: continue
                expected_tax=round(a*0.05)
                tax_ok=abs(b-expected_tax)<=1
                zero_tax_ok=(b==0)
                if not (tax_ok or zero_tax_ok):
                    continue
                freq=nums.count(a)+nums.count(b)+nums.count(t)
                score=(6 if tax_ok else 2)+min(freq,6)+(2 if a>=100 else 0)+(1 if t>=a else 0)
                triples.append((score,a,b,t))
        if triples:
            triples.sort(reverse=True)
            _,a,b,t=triples[0]
            actual["amount_before_tax"]=a
            actual["tax_amount"]=b
            actual["total_amount"]=t
            evidence["amount_arithmetic_candidate"]={"source":"page_tax_consistency","value":[a,b,t],"candidates":len(triples)}
    return actual,evidence

def parse_field(name: str, text: str):
    if name == "invoice_number": return parse_invoice_number(text)
    if name in {"buyer_tax_id","seller_tax_id"}: return parse_tax_id(text)
    if name == "amount_before_tax":
        return contextual_money(text,["銷售額合計","销售额合计","銷售額","销售额"]) or parse_money(text)
    if name == "tax_amount":
        return contextual_money(text,["營業稅","营业税"]) or parse_money(text)
    if name == "total_amount":
        return contextual_money(text,["總計新臺幣","总计新台币","總計","总计"]) or parse_money(text)
    if name == "invoice_date": return contextual_date(text)
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
    field_stats={}
    for case in manifest["cases"]:
        try:
            raw_image=Image.open(io.BytesIO(fetch(case["image_url"]))).convert("RGB")
            image,geometry=normalize_document(raw_image)
            page_text,page_conf=ocr_text(engine,image)
            template,tconf=classify(page_text,templates)
            actual={}; evidence={}
            mode="generic_fallback"
            if template:
                mode="template"
                template_hits += 1
                actual["document_type"]=template["document_type"]
                anchored,anchor_evidence=extract_template_fields(page_text,template["document_type"])
                actual.update(anchored)
                evidence.update(anchor_evidence)
                # ROI is now a secondary recovery path only. It must never overwrite an anchor-derived value.
                for field,box in template["regions"].items():
                    if field in actual and actual.get(field) is not None:
                        continue
                    text,conf=ocr_text(engine,crop_norm(image,box))
                    value=parse_field(field,text)
                    evidence[field]={"source":"roi_fallback","text":text[:500],"ocr_confidence":conf,"value":value}
                    if field != "items" and value is not None:
                        actual[field]=value
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
                stat=field_stats.setdefault(field,{"correct":0,"total":0})
                stat["total"] += 1
                stat["correct"] += int(ok)
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
            core_fields=("invoice_number","invoice_date","buyer_tax_id","seller_tax_id","total_amount")
            supported_core=[x for x in core_fields if x in case["expected"]]
            core_exact=all(checks.get(x,{}).get("ok") is True for x in supported_core)
            validation_values=[v for v in validation.values() if v is not None]
            validations_ok=all(v is True for v in validation_values)
            min_roi_conf=min(
                [float(v.get("ocr_confidence",page_conf) or page_conf) for k,v in evidence.items() if k in supported_core and isinstance(v,dict)] or [page_conf]
            )
            safe_auto_pass=bool(
                mode=="template" and tconf>=0.5 and core_exact and validations_ok and min_roi_conf>=0.72
            )
            row = {"id":case["id"],"mode":mode,"template_id":template["id"] if template else None,
                   "template_confidence":tconf,"page_ocr_confidence":page_conf,"geometry":geometry,
                   "actual":actual,"checks":checks,"validation":validation,
                   "safe_auto_pass":safe_auto_pass,"min_core_ocr_confidence":round(min_roi_conf,4),
                   "evidence":evidence}
            print("case_result="+json.dumps(row,ensure_ascii=False), flush=True)
            rows.append(row)
        except Exception as exc:
            rows.append({"id":case["id"],"error":type(exc).__name__+":"+str(exc)})
    for stat in field_stats.values():
        stat["accuracy"]=stat["correct"]/stat["total"] if stat["total"] else 0.0
    safe_passes=sum(1 for row in rows if row.get("safe_auto_pass"))
    unsafe_auto_passes=sum(
        1 for row in rows
        if row.get("safe_auto_pass") and any(not v.get("ok",False) for v in row.get("checks",{}).values())
    )
    summary={"engine":"rapidocr-template-router","cases":len(rows),"template_hits":template_hits,
             "template_hit_rate":template_hits/len(rows) if rows else 0.0,
             "checked_fields":total,"correct_fields":correct,
             "field_exact_match":correct/total if total else 0.0,
             "field_stats":field_stats,
             "safe_auto_passes":safe_passes,
             "safe_auto_pass_rate":safe_passes/len(rows) if rows else 0.0,
             "unsafe_auto_passes":unsafe_auto_passes,
             "rows":rows}
    print("template_router_summary="+json.dumps(summary,ensure_ascii=False))
    if args.out: Path(args.out).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
