#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from rapidocr import ModelType, RapidOCR

def compact(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())

def digits(value: str) -> str:
    return re.sub(r"\D", "", value)

def fetch(url: str) -> bytes:
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 invoice-benchmark/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        data=r.read(12*1024*1024+1)
    if not data or len(data)>12*1024*1024:
        raise RuntimeError("invalid_image")
    return data

def result_text(result) -> str:
    # RapidOCR 3.x returns an OCRResult object. Keep this tolerant across minor versions.
    if hasattr(result, "txts") and result.txts is not None:
        return "\n".join(str(x) for x in result.txts)
    if hasattr(result, "to_json"):
        raw=result.to_json()
        obj=json.loads(raw) if isinstance(raw,str) else raw
        for key in ("txts","texts","rec_texts"):
            if isinstance(obj,dict) and obj.get(key):
                return "\n".join(str(x) for x in obj[key])
    if isinstance(result,(list,tuple)):
        out=[]
        for item in result:
            if isinstance(item,(list,tuple)) and len(item)>=2:
                candidate=item[1]
                if isinstance(candidate,(list,tuple)) and candidate:
                    out.append(str(candidate[0]))
                elif isinstance(candidate,str):
                    out.append(candidate)
        return "\n".join(out)
    return str(result)

def check_field(field, expected, text):
    c=compact(text)
    d=digits(text)
    if field=="invoice_number":
        return compact(str(expected)) in c
    if field in {"total_amount","amount_before_tax","tax_amount","buyer_tax_id","seller_tax_id"}:
        return digits(str(expected)) in d
    if field=="invoice_date":
        y,m,day=[int(x) for x in str(expected).split("-")]
        roc=y-1911
        candidates=[
            f"{roc}{m}{day}",
            f"{roc:03d}{m:02d}{day:02d}",
            f"{y}{m}{day}",
            f"{y:04d}{m:02d}{day:02d}",
        ]
        return any(x in d for x in candidates)
    return False

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--out",default="")
    ap.add_argument("--model-size",choices=["small","medium"],default="small")
    args=ap.parse_args()

    manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    params={}
    if args.model_size=="medium":
        params={"Det.model_type":ModelType.MEDIUM,"Rec.model_type":ModelType.MEDIUM}
    engine=RapidOCR(params=params) if params else RapidOCR()
    rows=[]
    correct=total=0
    for case in manifest["cases"]:
        try:
            image=fetch(case["image_url"])
            result=engine(image)
            text=result_text(result)
            checks={}
            for field,expected in case["expected"].items():
                if field not in {"invoice_number","invoice_date","total_amount","amount_before_tax","tax_amount","buyer_tax_id","seller_tax_id"}:
                    continue
                ok=check_field(field,expected,text)
                checks[field]={"expected":expected,"ok":ok}
                total+=1
                correct+=int(ok)
            row={"id":case["id"],"checks":checks,"ocr_text":text[:5000]}
        except Exception as exc:
            row={"id":case["id"],"error":type(exc).__name__+":"+str(exc)}
        print(json.dumps(row,ensure_ascii=False))
        rows.append(row)

    summary={
        "engine":"rapidocr",
        "model_size":args.model_size,
        "cases":len(rows),
        "checked_fields":total,
        "correct_fields":correct,
        "field_recall":(correct/total if total else 0.0),
        "acceptance_target":0.90,
        "rows":rows
    }
    print("rapidocr_summary="+json.dumps(summary,ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
