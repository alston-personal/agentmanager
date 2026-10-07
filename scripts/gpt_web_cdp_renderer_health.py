#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

APP = Path(__file__).resolve().parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from gpt_web_response_bridge import _create_target, _open_target_connection

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args=ap.parse_args()

    target=_create_target(args.cdp_url,"about:blank")
    endpoint=None
    try:
        endpoint=_open_target_connection(args.cdp_url,target,expected_url_prefix="about:blank")
        value=endpoint.evaluate("1+1")
        payload={
            "schema":"agentos.gpt-web-cdp-renderer-health/v0.1",
            "ok": value == 2,
            "target_id": target.get("id"),
            "transport": endpoint.mode,
            "evaluate_result": value,
        }
        print(json.dumps(payload,ensure_ascii=False,sort_keys=True))
        return 0 if value == 2 else 42
    except Exception as exc:
        print(json.dumps({
            "schema":"agentos.gpt-web-cdp-renderer-health/v0.1",
            "ok":False,
            "target_id":target.get("id"),
            "error":f"{type(exc).__name__}: {exc}",
        },ensure_ascii=False,sort_keys=True))
        return 42
    finally:
        if endpoint is not None:
            endpoint.close()

if __name__=="__main__":
    raise SystemExit(main())
