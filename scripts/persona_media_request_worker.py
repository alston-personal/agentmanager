#!/usr/bin/env python3
"""Truthful, idempotent media-request intake for Mio's social lane."""
import argparse
import json
import os
import subprocess
import tempfile
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
            image_python=os.environ.get("AGENTOS_MIO_IMAGE_EXECUTOR_PYTHON","")
            image_script=os.environ.get("AGENTOS_MIO_IMAGE_EXECUTOR","")
            image_dir=os.environ.get("AGENTOS_MIO_MEDIA_OUTPUT_DIR","")
            outcome="CAPABILITY_UNAVAILABLE_IMAGE_GENERATION"
            if image_python and image_script and image_dir and Path(image_python).is_file() and Path(image_script).is_file():
                with tempfile.TemporaryDirectory(prefix="mio-media-receipt-") as temp:
                    result_path=Path(temp)/"generation.json"
                    try:
                        result=subprocess.run([image_python,image_script,"--request",str(path),
                            "--output-dir",image_dir,"--receipt",str(result_path)],
                            capture_output=True,text=True,timeout=180)
                        generation=load(result_path) if result_path.is_file() else {}
                        if result.returncode==0 and generation.get("status")=="GENERATED_UNVERIFIED":
                            now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
                            receipt_ref=f"pdca/media_receipts/{action_id}.json"
                            save(root/receipt_ref,{
                                "schema":"agentos.persona-media-worker-receipt/v1",
                                "action_id":action_id,"timestamp":now,"status":"GENERATED_UNVERIFIED",
                                "provider":generation.get("provider"),"image_path":generation.get("image_path"),
                                "image_sha256":generation.get("image_sha256"),
                                "reference_source":generation.get("reference_source"),
                                "generated":True,"asset_verified":False,"uploaded":False,
                                "publication_allowed":False})
                            request["status"]="generated_unverified"
                            request["receipt_ref"]=receipt_ref
                            request["checked_at"]=now
                            save(path,request)
                            state_path=root/"pdca/state.json"
                            state=load(state_path)
                            for action in state.get("pending_external_actions") or []:
                                if action.get("action_id")==action_id:
                                    media=action.get("media_intent") or {}
                                    media["status"]="generated_unverified"
                                    media["worker_receipt_ref"]=receipt_ref
                                    action["media_intent"]=media
                            save(state_path,state)
                            count+=1
                            continue
                        outcome="IMAGE_GENERATION_FAILED_"+str(generation.get("reason") or "unknown")[:80]
                    except (OSError,ValueError,subprocess.TimeoutExpired):
                        outcome="IMAGE_GENERATION_RUNTIME_FAILURE"
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
