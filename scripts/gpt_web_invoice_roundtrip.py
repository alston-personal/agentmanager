#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.gpt_web_response_bridge import process_one, refresh_sessions

EXPECTED = {
    "invoice_number": "MY04200253",
    "invoice_date": "2019-03-23",
    "seller_tax_id": "82328968",
    "total_amount": 50,
}

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--bridge-root", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args=ap.parse_args()

    root=args.bridge_root.expanduser().resolve()
    image=args.image.expanduser().resolve()
    if not image.is_file():
        raise FileNotFoundError(str(image))

    session_id=refresh_sessions(root,args.cdp_url)
    corr="invoice-roundtrip-my04200253"
    outer="session-invoice-roundtrip-my04200253"
    prompt=(
        'Read the attached Taiwan invoice image and return raw JSON only, no markdown. '
        'Include exactly "agentos_request_id":"' + corr + '". '
        'Extract invoice_number, invoice_date, seller_tax_id, total_amount. '
        'Do not guess unreadable values; use null.'
    )
    request={
        "schema":"agentos.session-request/v0.1",
        "request_id":outer,
        "provider":"gpt-web",
        "operation":"invoke",
        "session_id":session_id,
        "payload":{
            "schema":"agentos.gpt-web-vision-invoke/v0.1",
            "request_id":corr,
            "capability":"vision.invoice.extract",
            "image_path":str(image),
            "prompt":prompt,
        },
    }
    q=root/"requests"/f"{outer}.json"
    q.parent.mkdir(parents=True,exist_ok=True)
    q.write_text(json.dumps(request,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    process_one(root,args.cdp_url,q)

    receipt_path=root/"receipts"/f"{outer}.json"
    if not receipt_path.is_file():
        raise RuntimeError("roundtrip receipt missing")
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    print("gpt_web_invoice_roundtrip_receipt_ok="+str(bool(receipt.get("ok"))).lower())
    if not receipt.get("ok"):
        print("gpt_web_invoice_roundtrip_error="+str(receipt.get("error")))
        return 41

    result=receipt.get("result") or {}
    if result.get("request_id") != corr:
        raise RuntimeError("roundtrip correlation mismatch")
    text=str(result.get("assistant_text") or "").strip()
    payload=json.loads(text)
    if payload.get("agentos_request_id") != corr:
        raise RuntimeError("model correlation mismatch")

    for key,value in EXPECTED.items():
        got=payload.get(key)
        print(f"gpt_web_invoice_roundtrip_field={key} got={got} expected={value}")
        if str(got).replace(" ","").upper() != str(value).replace(" ","").upper():
            raise RuntimeError(f"field mismatch {key}: {got!r} != {value!r}")
    print("gpt_web_invoice_roundtrip=PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
