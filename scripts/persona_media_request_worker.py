#!/usr/bin/env python3
"""Truthful, idempotent media-request intake for Mio's social lane."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def process(root):
    requests=root/"pdca/media_requests"
    count=0
    for path in sorted(requests.glob("*.json")) if requests.exists() else []:
        request=load(path)
        if request.get("status")!="awaiting_media_executor":
            continue
        action_id=request.get("action_id")
        if not isinstance(action_id,str) or path.stem!=action_id:
            continue
        mode=request.get("mode")
        if mode not in ("generate","existing_verified"):
            continue
        missing=[p for p in ("visual_anchor_spec.json","visual_content_policy.json")
                 if not (root/p).is_file()]
        if missing:
            outcome="BLOCKED_MISSING_VISUAL_POLICY"
        elif mode=="generate":
            outcome="CAPABILITY_UNAVAILABLE_IMAGE_GENERATION"
        else:
            outcome="CAPABILITY_UNAVAILABLE_ASSET_RESOLVER"
        now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        receipt_ref=f"pdca/media_receipts/{action_id}.json"
        save(root/receipt_ref,{
            "schema":"agentos.persona-media-worker-receipt/v1",
            "action_id":action_id,"timestamp":now,
            "status":"BLOCKED","reason":outcome,
            "generated":False,"asset_verified":False,"uploaded":False
        })
        request["status"]="blocked"
        request["blocked_reason"]=outcome
        request["receipt_ref"]=receipt_ref
        request["checked_at"]=now
        save(path,request)
        state_path=root/"pdca/state.json"
        state=load(state_path)
        for action in state.get("pending_external_actions") or []:
            if action.get("action_id")==action_id:
                media=action.get("media_intent") or {}
                media["status"]="blocked"
                media["reason_code"]=outcome
                media["worker_receipt_ref"]=receipt_ref
                action["media_intent"]=media
        save(state_path,state)
        count+=1
    print(json.dumps({"media_requests_processed":count,"mode":"intake_only","generation_performed":False}))
    return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    return process(Path(args.persona_dir))

if __name__=="__main__":
    raise SystemExit(main())
