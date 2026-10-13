#!/usr/bin/env python3
"""Read-only independent acceptance preflight for Mio's exact NET trousers.
No approval or wardrobe writes. Checks candidate, source, registry and job.
"""
import hashlib, json, os, pathlib, sys
ROOT=pathlib.Path(os.environ.get("AGENT_DATA_ROOT",str(pathlib.Path.home()/"agent-data")))/"projects/dressup-simulator"
ID="net-31234-product-689961"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def test():
    record=load(ROOT/"garments/imported"/(ID+".json"))
    source_sha=record["source"]["sourceAssetSha256"]
    source=ROOT/"source_images"/source_sha/"original"
    folder=ROOT/"isolation_candidates"/ID/source_sha
    receipt=load(folder/"candidate-receipt.json")
    job=load(ROOT/"isolation_jobs"/(ID+".json"))
    checks={
      "registry_id":record.get("garmentId")==ID,
      "source_hash":source.is_file() and not source.is_symlink() and sha(source)==source_sha,
      "receipt_source":receipt.get("sourceAssetSha256")==source_sha and receipt.get("garmentId")==ID,
      "candidate_hash":(folder/"garment.png").is_file() and sha(folder/"garment.png")==receipt.get("isolatedAssetSha256"),
      "mask_hash":(folder/"garment.mask.png").is_file() and sha(folder/"garment.mask.png")==receipt.get("maskSha256"),
      "product_ir":receipt.get("productIR",{}).get("schema")=="agentos.wardrobe-product-ir/v1" and receipt.get("productIR",{}).get("category")=="lower_main",
      "pending_review":receipt.get("review",{}).get("state")=="pending" and receipt.get("approved") is False,
      "job_candidate":job.get("state")=="candidate",
    }
    status="PASS" if all(checks.values()) else "FAIL"
    print(json.dumps({"schema":"agentos.mio-wardrobe-preflight/v1","garmentId":ID,
      "integrity":status,"checks":checks,"approved":False,
      "nextGate":"independent_visual_QA_and_approved_asset_delivery",
      "sourceSha256":source_sha,"candidateSha256":receipt.get("isolatedAssetSha256"),
      "maskSha256":receipt.get("maskSha256")},ensure_ascii=False))
    return 0 if status=="PASS" else 2
if __name__=="__main__":sys.exit(test())
