#!/usr/bin/env python3
"""Install a candidate garment alpha PNG and mask into immutable Oracle staging.

No try-on permission, no automatic approval. The protected Debug API can
read the bytes and independent reviewers can verify them before promotion.
"""
import argparse,hashlib,json,os,re,tempfile
from pathlib import Path

ROOT=Path(os.environ.get("AGENT_DATA_ROOT",str(Path.home()/"agent-data")))/"projects/dressup-simulator"
GARMENT="net-31234-product-689961"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def persist(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=path.parent,delete=False,encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
        tmp=Path(f.name)
    os.chmod(tmp,0o600)
    os.replace(tmp,path)

def run(folder:Path,source_sha:str):
    if not re.fullmatch("[a-f0-9]{64}",source_sha):
        raise ValueError("invalid_source_sha")
    canonical=ROOT/"garments"/"imported"/(GARMENT+".json")
    source=ROOT/"source_images"/source_sha/"original"
    record=json.loads(canonical.read_text(encoding="utf-8"))
    if record.get("garmentId")!=GARMENT or (record.get("source") or {}).get("sourceAssetSha256")!=source_sha:
        raise ValueError("garment_registry_source_mismatch")
    if not source.is_file() or sha(source)!=source_sha:
        raise ValueError("immutable_source_missing_or_corrupt")
    job_path=ROOT/"isolation_jobs"/(GARMENT+".json")
    job=json.loads(job_path.read_text(encoding="utf-8"))
    if job.get("state")=="approved" or (record.get("tryOnSource") or {}).get("state")=="approved":
        raise ValueError("approved_item_cannot_be_overwritten")
    receipt=json.loads((folder/"candidate-receipt.json").read_text(encoding="utf-8"))
    if (receipt.get("schema")!="agentos.wardrobe-isolation-candidate/v1"
        or receipt.get("garmentId")!=GARMENT
        or receipt.get("sourceAssetSha256")!=source_sha
        or receipt.get("approved") is not False
        or receipt.get("review",{}).get("state")!="pending"):
        raise ValueError("invalid_candidate_receipt")
    target=ROOT/"isolation_candidates"/GARMENT/source_sha
    for name,digest in (("garment.png","isolatedAssetSha256"),("garment.mask.png","maskSha256")):
        source_artifact=folder/name
        if not source_artifact.is_file() or source_artifact.is_symlink() or sha(source_artifact)!=receipt.get(digest):
            raise ValueError("candidate_asset_digest_mismatch")
        if source_artifact.stat().st_size>15_000_000:raise ValueError("asset_too_large")
        target.mkdir(parents=True,exist_ok=True)
        destination=target/name
        if destination.exists():
            if destination.is_symlink() or sha(destination)!=receipt[digest]:
                raise ValueError("candidate_version_conflict")
        else:
            with tempfile.NamedTemporaryFile(dir=target,delete=False) as f:
                f.write(source_artifact.read_bytes())
                tmp=Path(f.name)
            os.chmod(tmp,0o600)
            os.replace(tmp,destination)
    target_receipt=target/"candidate-receipt.json"
    if target_receipt.exists():
        existing=json.loads(target_receipt.read_text(encoding="utf-8"))
        if existing.get("isolatedAssetSha256")!=receipt["isolatedAssetSha256"]:
            raise ValueError("immutable_candidate_receipt_conflict")
    else:
        persist(target_receipt,receipt)
    if job.get("state") in ("pending","extracting"):
        job["state"]="candidate"
        job["candidateSourceAssetSha256"]=source_sha
        persist(job_path,job)
    return {"garmentId":GARMENT,"state":"candidate","approved":False,
            "sourceSha256":source_sha,"isolatedAssetSha256":receipt["isolatedAssetSha256"],
            "maskSha256":receipt["maskSha256"],"debugSourceAvailable":True}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--folder",required=True,type=Path)
    p.add_argument("--source-sha256",required=True)
    a=p.parse_args()
    print(json.dumps(run(a.folder,a.source_sha256),ensure_ascii=False))
