#!/usr/bin/env python3
"""Atomically register verified NET vendor source photos to Mio's canonical wardrobe.

Inputs must contain the real downloaded image bytes and digest from the CDN
probe. Creates immutable source snapshots, canonical imported garment records,
pending isolation jobs, and receipts. Never auto-approves a try-on asset.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))) / "projects/dressup-simulator"
IMAGE_TYPES = {"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}
ID = re.compile(r"[A-Za-z0-9._-]{1,160}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        temp = Path(f.name)
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def copy_immutable(original, destination, sha):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest()!=sha:
            raise ValueError("source_hash_collision_or_corruption")
        return
    with tempfile.NamedTemporaryFile(dir=destination.parent,delete=False) as f:
        with original.open("rb") as src:
            shutil.copyfileobj(src,f)
        tmp=Path(f.name)
    try:
        if hashlib.sha256(tmp.read_bytes()).hexdigest()!=sha:
            raise ValueError("source_changed")
        os.chmod(tmp, 0o600)
        os.replace(tmp,destination)
    finally:
        tmp.unlink(missing_ok=True)


def stage_product(row, product, bundle):
    garment_id=row["garmentId"]
    if not ID.fullmatch(garment_id):
        raise ValueError("invalid_garment_id")
    if product["garmentId"]!=garment_id or product["productId"]!=row["productId"]:
        raise ValueError("manifest_identity_mismatch")
    if row.get("variantCode")!=product.get("variantCode") or not row.get("variantCode"):
        raise ValueError("unverified_product_variant")
    images=product.get("images",[])
    if not images:
        raise ValueError("source_image_missing")
    photo=images[0]
    sha=photo["imageSha256"]
    if not DIGEST.fullmatch(sha):
        raise ValueError("invalid_source_hash")
    url=photo["sourceUrl"]
    expected=f"/act/{row['productId']}-{row['variantCode']}-1024-"
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname!="s-net.wimg.tw" or expected not in parsed.path:
        raise ValueError("unverified_vendor_image_url")
    ext=IMAGE_TYPES.get(photo.get("contentType"))
    if not ext: raise ValueError("unverified_image_type")
    source=bundle/garment_id/(sha+"."+ext)
    if not source.is_file() or source.is_symlink():
        raise ValueError("source_bytes_missing")
    if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
        raise ValueError("source_digest_mismatch")
    snapshot=ROOT/"source_images"/sha/"original"
    target=ROOT/"garments"/"imported"/(garment_id+".json")
    if target.exists() and not target.is_symlink():
        existing=json.loads(target.read_text(encoding="utf-8"))
        existing_source=(existing.get("source") or {})
        previous_sha=existing_source.get("sourceAssetSha256")
        if (existing.get("garmentId")==garment_id
            and existing.get("characterId")=="sunlake-milkcat-ai-001"
            and existing_source.get("imageUrl")==url
            and isinstance(previous_sha,str) and DIGEST.fullmatch(previous_sha)
            and (ROOT/"source_images"/previous_sha/"original").is_file()
            and (ROOT/"isolation_jobs"/(garment_id+".json")).is_file()):
            canonical=ROOT/"source_images"/previous_sha/"original"
            if hashlib.sha256(canonical.read_bytes()).hexdigest()!=previous_sha:
                raise ValueError("canonical_source_snapshot_corrupted")
            # CDN responses may be re-encoded with identical visual pixels.
            # Never churn already-registered immutable bytes on retries.
            return {"garmentId":garment_id,"state":"awaiting_isolation",
                    "sourceSha256":previous_sha,"sourceUrl":url,
                    "approved":False,"sourceSnapshotExists":True,
                    "idempotent":True}
    copy_immutable(source,snapshot,sha)
    if target.exists():
        if target.is_symlink(): raise ValueError("unsafe_registry_record")
        record=json.loads(target.read_text(encoding="utf-8"))
        if record.get("garmentId")!=garment_id or record.get("characterId")!="sunlake-milkcat-ai-001":
            raise ValueError("registry_identity_conflict")
        existing_url=(record.get("source") or {}).get("imageUrl")
        if existing_url and existing_url!=url:
            raise ValueError("existing_vendor_image_requires_review")
        if (record.get("tryOnSource") or {}).get("state")=="approved":
            return {"garmentId":garment_id,"state":"existing_approved_preserved","sourceSha256":sha}
    else:
        record={
            "schema":"agentos.garment/v1","garmentId":garment_id,
            "characterId":"sunlake-milkcat-ai-001",
            "name":row["name"],"retailer":"NET","brand":"NET",
            "sku":row["productId"],"variant":row["variantCode"],
            "slot":row["slot"],"layer":row["slot"],
            "acquisition":{"state":"want_to_try","owned":False,"worn":False},
            "tryOn":{"state":"awaiting_isolation","asset":None}}
    source_info=record.setdefault("source",{})
    source_info.update({"productUrl":row["productUrl"],"imageUrl":url,
                        "officialVisualUrl":url,
                        "sourceAssetSha256":sha,
                        "sourceCaptureMethod":"validated_net_cdn_sku_variant",
                        "sourceVerifiedAt":"2026-10-13"})
    record["thumbnailUrl"]=url
    record.setdefault("tryOnSource",{"schema":"agentos.wardrobe-isolated-product/v1",
             "state":"pending","isolatedImageUrl":None,
             "maskUrl":None,"productIR":None,
             "sourceFingerprint":hashlib.sha256(url.encode()).hexdigest()})
    task_path=ROOT/"isolation_jobs"/(garment_id+".json")
    if task_path.exists():
        task=json.loads(task_path.read_text(encoding="utf-8"))
        if task.get("state")=="approved":
            raise ValueError("immutable_approved_job")
        if task.get("sourceFingerprint")!=hashlib.sha256(url.encode()).hexdigest():
            raise ValueError("source_changed_requires_review")
    else:
        task={"schema":"agentos.wardrobe-isolation-job/v1",
          "garmentId":garment_id,"state":"pending","targetLayer":row["slot"],
          "productName":row["name"],"sourceImageUrl":url,
          "sourceFingerprint":hashlib.sha256(url.encode()).hexdigest(),
          "sourceAssetSha256":sha,"approved":False,
          "requirements":{"singleTargetObject":True,"isolatedImageMustBeVerified":True}}
    # Write task before record. If interrupted, recovery can replay same input.
    atomic_json(task_path,task)
    atomic_json(target,record)
    return {"garmentId":garment_id,"state":"awaiting_isolation",
            "sourceSha256":sha,"sourceUrl":url,
            "approved":False,"sourceSnapshotExists":snapshot.is_file()}


def stage(manifest,bundle):
    spec=json.loads(manifest.read_text(encoding="utf-8"))
    report=json.loads((bundle/"report.json").read_text(encoding="utf-8"))
    if spec.get("schema")!="agentos.mio-net-source-backfill/v1" or report.get("schema")!="agentos.mio-net-cdn-probe/v1":
        raise ValueError("invalid_source_schemas")
    indexed={x["garmentId"]:x for x in report["products"]}
    receipts=[]
    for row in spec["items"]:
        source=indexed.get(row["garmentId"])
        try:
            if source and source["state"]=="candidate_images_found":
                receipt=stage_product(row,source,bundle)
            else:
                receipt={"garmentId":row["garmentId"],"state":"source_pending",
                         "approved":False}
        except Exception as exc:
            receipt={"garmentId":row["garmentId"],"state":"needs_review",
                     "errorType":type(exc).__name__,"approved":False}
        atomic_json(ROOT/"source_sync_receipts"/(row["garmentId"]+".json"),receipt)
        receipts.append(receipt)
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    return receipts


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--bundle",type=Path,required=True)
    a=p.parse_args()
    receipts=stage(a.manifest,a.bundle)
    print("mio_source_staged="+str(sum(r["state"]=="awaiting_isolation" for r in receipts)))
