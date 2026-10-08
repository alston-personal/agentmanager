#!/usr/bin/env python3
"""Append-only capability experience ledger: evidence, not optimistic success labels."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STATES={"DECLARED","ATTEMPTED","FAILED","OUTPUT_OBSERVED","VERIFIED_SUCCESS"}
def classify(r):
    s=str(r.get("status") or "").upper()
    if s in ("BLOCKED","FAILED","ERROR"): return "FAILED"
    if s=="GENERATED_UNVERIFIED" and r.get("image_sha256"): return "OUTPUT_OBSERVED"
    if s=="EXECUTED" and r.get("write_performed") is True and r.get("provider_receipt",{}).get("ok") is True: return "VERIFIED_SUCCESS"
    return "ATTEMPTED"

def record(event,ledger):
    if event.get("evidence_kind") not in ("source_code","git_artifact","runtime_receipt"):
        raise ValueError("evidence_kind_invalid")
    if not event.get("source_ref") or not event.get("capability"):
        raise ValueError("evidence_reference_required")
    state=event.get("outcome")
    if state not in STATES: raise ValueError("outcome_invalid")
    if event["evidence_kind"]=="source_code" and state!="DECLARED":
        raise ValueError("source_code_is_not_runtime_proof")
    if event["evidence_kind"]=="git_artifact" and state not in ("OUTPUT_OBSERVED",):
        raise ValueError("asset_is_not_provider_success_proof")
    if state=="VERIFIED_SUCCESS" and event["evidence_kind"]!="runtime_receipt":
        raise ValueError("verified_success_requires_runtime_receipt")
    row={"schema":"agentos.capability-experience/v1",**event}
    canonical=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    row["evidence_id"]=hashlib.sha256(canonical.encode()).hexdigest()
    ledger.parent.mkdir(parents=True,exist_ok=True)
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if json.loads(line).get("evidence_id")==row["evidence_id"]:
                return {"status":"DUPLICATE","evidence_id":row["evidence_id"]}
    with ledger.open("a",encoding="utf-8") as f:
        f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    return {"status":"RECORDED","evidence_id":row["evidence_id"]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ledger",required=True)
    parser.add_argument("--event",required=True)
    args=parser.parse_args()
    print(json.dumps(record(json.loads(Path(args.event).read_text(encoding="utf-8")),Path(args.ledger))))
if __name__=="__main__": main()
