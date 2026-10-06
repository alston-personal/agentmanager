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

def call(name, body, revision=None, query_key=False):
    headers={"Content-Type":"application/json"}
    url=ENDPOINT
    if query_key:
        url += "?key=" + KEY
    else:
        headers["x-goog-api-key"]=KEY
    if revision:
        headers["Api-Revision"]=revision
    req=urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            raw=r.read(256*1024)
        env=json.loads(raw)
        print(f"probe={name} http=200 output_text={bool(env.get('output_text'))} status={env.get('status')}")
        return True
    except urllib.error.HTTPError as exc:
        status=None
        message=None
        try:
            payload=json.loads(exc.read(64*1024))
            error=payload.get("error")
            if isinstance(error,dict):
                status=error.get("status")
                message=str(error.get("message") or "")[:500].replace("\n"," ")
            else:
                message=str(error)[:500].replace("\n"," ")
        except Exception:
            pass
        ctype=exc.headers.get("Content-Type") if exc.headers else None
        server=exc.headers.get("Server") if exc.headers else None
        print(f"probe={name} http={exc.code} google_status={status} content_type={ctype} server={server} message={message}")
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
    try:
        req=urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key":KEY},
        )
        with urllib.request.urlopen(req,timeout=30) as response:
            print(f"probe=models_list http={response.status} content_type={response.headers.get('Content-Type')}")
    except urllib.error.HTTPError as exc:
        print(f"probe=models_list http={exc.code} content_type={exc.headers.get('Content-Type') if exc.headers else None}")

    cases=[
      ("text_plain",{"model":MODEL,"input":"Return the integer 50."}),
      ("text_plain_query_key",{"model":MODEL,"input":"Return the integer 50."}),
      ("text_plain_revision",{"model":MODEL,"input":"Return the integer 50."}),
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
        revision="2026-05-20" if name=="text_plain_revision" else None
        query_key=name=="text_plain_query_key"
        ok=call(name,body,revision=revision,query_key=query_key) and ok
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
