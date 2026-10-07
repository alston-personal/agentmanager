#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from services.invoice_intake.template_ocr import extract_template_invoice

FIELDS = (
    "invoice_number","invoice_date","seller_tax_id",
    "amount_before_tax","tax_amount","total_amount",
)
MONEY = {"amount_before_tax","tax_amount","total_amount"}

def fetch(url:str)->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 invoice-template-benchmark/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        data=r.read(12*1024*1024+1)
    if not data or len(data)>12*1024*1024:
        raise RuntimeError("invalid_image")
    return data

def norm(field:str,value:Any)->str:
    if field=="invoice_number":
        return re.sub(r"[^A-Z0-9]","",str(value or "").upper())
    if field=="invoice_date":
        return str(value or "")
    return re.sub(r"\D","",str(value or ""))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--out",default="")
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows=[]
    correct=total=money_correct=money_total=errors=0
    for case in manifest["cases"]:
        try:
            fixture=case.get("fixture_path")
            image=(root/fixture).read_bytes() if fixture and (root/fixture).is_file() else fetch(case["image_url"])
            result=extract_template_invoice(image)
            fields=result.get("fields") or {}
            checks={}
            for field,expected in case.get("expected",{}).items():
                if field not in FIELDS:
                    continue
                actual=fields.get(field)
                ok=norm(field,actual)==norm(field,expected)
                checks[field]={"expected":expected,"actual":actual,"ok":ok}
                total+=1; correct+=int(ok)
                if field in MONEY:
                    money_total+=1; money_correct+=int(ok)
            rows.append({
                "id":case["id"],
                "matched":result.get("matched"),
                "checks":checks,
                "amount_sources":result.get("amount_sources") or {},
                "row_reocr_evidence":result.get("row_reocr_evidence") or {},
            })
        except Exception as exc:
            errors+=1
            rows.append({"id":case["id"],"error":type(exc).__name__+":"+str(exc)})
    summary={
        "schema":"invoice-template-benchmark/v1",
        "cases":len(rows),
        "errors":errors,
        "field_exact_match":correct/total if total else 0.0,
        "money_exact_match":money_correct/money_total if money_total else None,
        "correct":correct,"total":total,
        "money_correct":money_correct,"money_total":money_total,
        "rows":rows,
    }
    rendered=json.dumps(summary,ensure_ascii=False,indent=2)
    print("template_benchmark_summary="+json.dumps(summary,ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(rendered,encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
