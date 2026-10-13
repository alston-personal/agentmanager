#!/usr/bin/env python3
"""Quarantine one visually rejected Mio try-on job without erasing evidence.

The actual rendered image is shorts rather than exact NET 31234-014 long
trousers. Original job, visual asset and prior quality receipt are preserved.
Invalidate only the exact rejected job and cache meta, never garment approval.
"""
import hashlib,json,os,pathlib,tempfile
from datetime import datetime,timezone
ROOT=pathlib.Path(os.environ.get("AGENT_DATA_ROOT",str(pathlib.Path.home()/"agent-data")))/"projects/dressup-simulator"
JOB="sunlake-milkcat-ai-001-tryon-2026-10-13T08-36-43-176Z-cde673e9"
GARMENT="net-31234-product-689961"
ASSET_SHA="7e899176e1b17002eb53dfeec71be8d796eefd0ae3c396ef953fdec96ed65d61"
def atomic(path,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as f:
        json.dump(row,f,ensure_ascii=False,indent=2)
        f.write("\n")
        tmp=pathlib.Path(f.name)
    os.chmod(tmp,0o600)
    tmp.replace(path)
def run():
    file=ROOT/"render_jobs/runtime"/(JOB+".json")
    record=json.loads(file.read_text(encoding="utf-8"))
    if record.get("jobId")!=JOB or (record.get("outfitIr") or {}).get("selectedLayers",{}).get("lower_main")!=GARMENT:
        raise ValueError("target_job_identity_mismatch")
    img=ROOT/"render_assets"/(JOB+".webp")
    if not img.is_file() or hashlib.sha256(img.read_bytes()).hexdigest()!=ASSET_SHA:
        raise ValueError("actual_render_asset_hash_mismatch")
    evidence=ROOT/"render_quality_rejections"/(JOB+".json")
    if not evidence.exists():
        atomic(evidence,{
           "schema":"agentos.wardrobe-visual-rejection/v1",
           "jobId":JOB,"garmentId":GARMENT,"actualRenderSha256":ASSET_SHA,
           "review":"VISUAL_REJECTED",
           "reason":"PRODUCT_IDENTITY_MISMATCH_LONG_TROUSERS_RENDERED_AS_SHORTS",
           "observations":["source product is dark full-length tapered trousers",
                           "render depicts light-grey shorts and bare legs",
                           "neutral-standing body/pose reference not preserved"],
           "originalStatus":record.get("status"),
           "originalQuality":(record.get("output") or {}).get("quality"),
           "originalProvider":(record.get("output") or {}).get("provider"),
           "originalRenderedLayers":(record.get("output") or {}).get("renderedLayers"),
           "originalPendingLayers":(record.get("output") or {}).get("pendingLayers"),
           "checkedAt":datetime.now(timezone.utc).isoformat(),
        })
    else:
        previous=json.loads(evidence.read_text(encoding="utf-8"))
        if previous.get("actualRenderSha256")!=ASSET_SHA:raise ValueError("rejection_evidence_conflict")
    print(json.dumps({"qa_audit_before_quarantine":{
      "status":record.get("status"),
      "provider":(record.get("output") or {}).get("provider"),
      "quality":(record.get("output") or {}).get("quality"),
      "renderedLayers":(record.get("output") or {}).get("renderedLayers"),
      "pendingLayers":(record.get("output") or {}).get("pendingLayers")}},ensure_ascii=False))
    if record.get("status") not in ("ready","failed"):
        raise ValueError("unexpected_render_job_state")
    record["status"]="failed"
    record["failedAt"]=datetime.now(timezone.utc).isoformat()
    record["error"]={"code":"PRODUCT_IDENTITY_MISMATCH","message":"Independent visual QA rejected: NET long trousers rendered as shorts"}
    output=record.setdefault("output",{})
    quality=output.setdefault("quality",{})
    quality.update({"state":"rejected","accepted":False,
                    "reviewer":"independent-visual-rejection-20261013",
                    "checkedAt":record["failedAt"]})
    output["asset"]=None
    output["previewAsset"]=None
    record["progress"]={"stage":"failed","heartbeatAt":record["failedAt"],
                         "message":"Visual QA: rejected wrong trousers"}
    atomic(file,record)
    key=output.get("cacheKey")
    if isinstance(key,str) and len(key)==64 and all(c in '0123456789abcdef' for c in key):
        meta=ROOT/"render_cache"/(key+".json")
        if meta.is_file():
            cached=json.loads(meta.read_text(encoding="utf-8"))
            cached.update({"qualityAccepted":False,"qualityState":"rejected",
                           "rejectedBy":JOB,"rejectionCode":"PRODUCT_IDENTITY_MISMATCH"})
            atomic(meta,cached)
    current=ROOT/"current_outfits"/"sunlake-milkcat-ai-001.json"
    if current.is_file():
        now=json.loads(current.read_text(encoding="utf-8"))
        if (now.get("tryOn") or {}).get("jobId")==JOB:
            now["updatedAt"]=record["failedAt"]
            now["tryOn"].update({"status":"failed","asset":None,"previewAsset":None,
                                 "qualityState":"rejected"})
            atomic(current,now)
    print(json.dumps({"jobId":JOB,"state":"visual_rejected","publicApprovedGarmentPreserved":True,
                      "originalQualityEvidenceSaved":True,"cacheRevoked":True},ensure_ascii=False))
if __name__=="__main__":run()
