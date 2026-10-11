#!/usr/bin/env python3
"""Truthful, idempotent media-request intake for Mio's social lane."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from capability_experience_ledger import record, classify

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def record_media_experience(root, receipt_ref, receipt):
    outcome=classify(receipt)
    record({
        "capability":"image.edit.flux-kontext" if receipt.get("provider") else "persona.media.prepare",
        "provider":receipt.get("provider") or "unresolved",
        "evidence_kind":"runtime_receipt",
        "source_ref":receipt_ref,
        "outcome":outcome,
        "action_id":receipt.get("action_id"),
        "timestamp":receipt.get("timestamp"),
        "failure_reason":receipt.get("reason"),
        "image_sha256":receipt.get("image_sha256"),
        "publication_allowed":False
    },root/"pdca/capability_experience.jsonl")

def process(root):
    root=root.resolve()
    requests=root/"pdca/media_requests"
    count=0
    # The existing validator consumes independently produced review evidence.
    # A generator never fills identity/rights checks or approves its own output.
    for path in sorted(requests.glob("*.json")) if requests.exists() else []:
        request=load(path)
        action_id=request.get("action_id")
        if not isinstance(action_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",action_id) or path.stem!=action_id:
            continue
        if request.get("status")=="asset_validated":
            continue
        state_path=root/"pdca/state.json"
        state=load(state_path)
        action=next((x for x in state.get("pending_external_actions") or []
                     if x.get("action_id")==action_id and x.get("capability")=="social.post.publish"
                     and x.get("status")=="candidate" and (x.get("media_intent") or {}).get("mode")==request.get("mode")
                     and request.get("mode") in ("generate","existing_verified")),None)
        review=root/"pdca/media_reviews"/(action_id+".json")
        if not action or not review.is_file():
            continue
        try:
            from persona_media_asset import prepare_asset
            output=os.environ.get("AGENTOS_MIO_PUBLIC_MEDIA_DIR","")
            if not output:
                raise ValueError("MEDIA_HOST_NOT_CONFIGURED")
            receipt=prepare_asset(root,action,review,output)
        except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired):
            # Raw errors can include filesystem/provider details. Leave a
            # sanitized hold, never replace a failed review with text only.
            if request.get("review_status")=="blocked":
                continue
            request["review_status"]="blocked"
            request["review_reason"]="MEDIA_REVIEW_OR_HOSTING_FAILED"
            save(path,request)
            count+=1
            continue
        receipt_ref=f"pdca/media_receipts/{action_id}-validated.json"
        receipt["timestamp"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        save(root/receipt_ref,receipt)
        media=action.get("media_intent") or {}
        media.update(status="validated",asset_receipt_ref=receipt_ref)
        action["media_intent"]=media
        save(state_path,state)
        request.update(status="asset_validated",review_status="pass",asset_receipt_ref=receipt_ref)
        save(path,request)
        count+=1
    for path in sorted(requests.glob("*.json")) if requests.exists() else []:
        request=load(path)
        if request.get("status")!="awaiting_media_executor":
            continue
        action_id=request.get("action_id")
        if not isinstance(action_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",action_id) or path.stem!=action_id:
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
                        generated_path=Path(generation.get("image_path") or "")
                        actual_output=(generated_path.is_file() and generated_path.resolve().is_relative_to(Path(image_dir).resolve())
                            and hashlib.sha256(generated_path.read_bytes()).hexdigest()==generation.get("image_sha256"))
                        if result.returncode==0 and generation.get("status")=="GENERATED_UNVERIFIED" and actual_output:
                            now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
                            receipt_ref=f"pdca/media_receipts/{action_id}.json"
                            save(root/receipt_ref,{
                                "schema":"agentos.persona-media-worker-receipt/v1",
                                "action_id":action_id,"timestamp":now,"status":"GENERATED_UNVERIFIED",
                                "provider":generation.get("provider"),"image_path":generation.get("image_path"),
                                "image_sha256":generation.get("image_sha256"),
                                "reference_image_sha256":generation.get("reference_image_sha256"),
                                "generated":True,"asset_verified":False,"uploaded":False,
                                "publication_allowed":False})
                            record_media_experience(root,receipt_ref,load(root/receipt_ref))
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
        record_media_experience(root,receipt_ref,load(root/receipt_ref))
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
    print(json.dumps({"media_requests_processed":count,"mode":"media_request_worker","experience_ledger":"pdca/capability_experience.jsonl"}))
    return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    return process(Path(args.persona_dir))

if __name__=="__main__":
    raise SystemExit(main())
