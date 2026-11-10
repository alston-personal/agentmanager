#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

VALID_STATES={
    "SOURCE_READY","CI_VERIFIED","DEPLOY_QUEUED","DEPLOY_FAILED",
    "DEPLOYED_UNVERIFIED","PRODUCTION_VERIFIED",
}

@dataclass
class Acceptance:
    url:str
    http_status:int|None
    body_sha256:str|None
    marker:str|None
    marker_found:bool|None
    differs_from_home:bool|None
    ok:bool
    error:str|None=None

def fetch(url:str)->tuple[int,bytes]:
    req=Request(url,headers={"User-Agent":"AgentOS-Production-Acceptance/1.0"})
    with urlopen(req,timeout=20) as r:
        return int(getattr(r,"status",200)),r.read(2_000_000)

def accept_web(url:str,marker:str|None,home_url:str|None)->Acceptance:
    try:
        status,body=fetch(url)
        sha=hashlib.sha256(body).hexdigest()
        found=(marker.encode("utf-8") in body) if marker else None
        differs=None
        if home_url:
            _,home=fetch(home_url)
            differs=hashlib.sha256(home).hexdigest()!=sha
        ok=200<=status<300 and (found is not False) and (differs is not False)
        return Acceptance(url,status,sha,marker,found,differs,ok)
    except (URLError,HTTPError,TimeoutError,OSError) as exc:
        return Acceptance(url,None,None,marker,None,None,False,type(exc).__name__)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",required=True)
    ap.add_argument("--marker")
    ap.add_argument("--home-url")
    ap.add_argument("--json",action="store_true")
    args=ap.parse_args()
    result=accept_web(args.url,args.marker,args.home_url)
    payload=asdict(result)
    payload["state"]="PRODUCTION_VERIFIED" if result.ok else "DEPLOYED_UNVERIFIED"
    if args.json:
        print(json.dumps(payload,ensure_ascii=False,indent=2))
    else:
        for k,v in payload.items():
            print(f"{k}={v}")
    return 0 if result.ok else 1

if __name__=="__main__":
    raise SystemExit(main())
