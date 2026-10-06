#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, urllib.error, urllib.request
from pathlib import Path

ENDPOINT="https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL=os.environ.get("GEMINI_INVOICE_MODEL","gemini-3.8-flash")
KEY=os.environ.get("GEMINI_API_KEY","").strip()
SCHEMA={
  "type":"object",
  "properties":{"value":{"type":["integer","null"]}},
  "required":["value"],
  "additionalProperties":False,
}

def call(name, body):
    req=urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type":"application/json","x-goog-api-key":KEY},
    )
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read(256*1024)
        env=json.loads(raw)
        print(f"probe={name} http=200 output_text={bool(env.get('output_text'))} status={env.get('status')}")
        return True
    except urllib.error.HTTPError as exc:
        status=None
        try:
            payload=json.loads(exc.read(64*1024))
            status=((payload.get("error") or {}).get("status"))
        except Exception:
            pass
        print(f"probe={name} http={exc.code} google_status={status}")
        return False
    except Exception as exc:
        print(f"probe={name} transport={type(exc).__name__}")
        return False

def main():
    if not KEY:
        print("probe=credential missing=true")
        return 2
    image=Path("benchmarks/invoice_handwriting/fixtures/tw-2part-my04200253.jpg").read_bytes()
    encoded=base64.b64encode(image).decode("ascii")
    cases=[
      ("text_plain",{"model":MODEL,"input":"Return the integer 50."}),
      ("image_plain",{"model":MODEL,"input":[
          {"type":"text","text":"Read the total amount only."},
          {"type":"image","data":encoded,"mime_type":"image/jpeg"},
      ]}),
      ("text_structured",{"model":MODEL,"input":"Return the integer 50.",
          "response_format":{"type":"text","mime_type":"application/json","schema":SCHEMA}}),
      ("image_structured",{"model":MODEL,"input":[
          {"type":"text","text":"Read the total amount only."},
          {"type":"image","data":encoded,"mime_type":"image/jpeg"},
      ],"response_format":{"type":"text","mime_type":"application/json","schema":SCHEMA}}),
    ]
    ok=True
    for name,body in cases:
        ok=call(name,body) and ok
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
