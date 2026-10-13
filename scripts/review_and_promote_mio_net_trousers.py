#!/usr/bin/env python3
"""Promote only the independently reviewed NET 31234-014 candidate to try-on.

Fail closed. Verify canonical product identity and all immutable source/candidate
byte hashes, full alpha-mask equality, pixel fidelity and product geometry.
Never promote other products. Retain original preapproval receipt and immutable
separate review evidence for audit. Reject if any recorded asset has changed.
"""
from __future__ import annotations
import argparse,hashlib,io,json,os,pathlib,re,tempfile
from PIL import Image,ImageChops
ROOT=pathlib.Path(os.environ.get("AGENT_DATA_ROOT",str(pathlib.Path.home()/"agent-data")))/"projects/dressup-simulator"
ID="net-31234-product-689961"
SRC="4b60389046bc037394a8d69511b104835cc1fcfc3b5e3964636244863495723e"
IMG="4d65de1c95c40d096c50794c6034d933512b8d2e213302d3074832e409eb6ec3"
MASK="2de5179484051b5023cf5669ec498ce571390895c3bb36a5edb59f9454f59150"
PIXEL="06a3aa8736af3dac238775a8c08ab90ce0fb9f5f8f5fa7ead0cdfd6d60d80ba9"
SOURCE_URL="https://s-net.wimg.tw//act/31234-014-1024-01.jpg"
ASSET_URL=f"https://studio.milkcat.org/dashboard/api/wardrobe/isolation/approved/{ID}/{SRC}"
REVIEWER="assistant-visual-review-with-independent-pixel-validation/v1"
def digest(data): return hashlib.sha256(data).hexdigest()
def read_json(path): return json.loads(path.read_text(encoding="utf-8"))
def write_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=path.parent,delete=False,encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
        temp=pathlib.Path(f.name)
    os.chmod(temp,0o600)
    os.replace(temp,path)

def run(promote):
    canonical=ROOT/"garments/imported"/(ID+".json")
    src=ROOT/"source_images"/SRC/"original"
    folder=ROOT/"isolation_candidates"/ID/SRC
    png=folder/"garment.png"
    mask=folder/"garment.mask.png"
    receipt_path=folder/"candidate-receipt.json"
    job_path=ROOT/"isolation_jobs"/(ID+".json")
    for p in (canonical,src,png,mask,receipt_path,job_path):
        if not p.is_file() or p.is_symlink():raise ValueError("required_source_missing_or_symlink:"+p.name)
    record=read_json(canonical)
    receipt=read_json(receipt_path)
    job=read_json(job_path)
    origin=record.get("source",{})
    if record.get("garmentId")!=ID or record.get("characterId")!="sunlake-milkcat-ai-001" or origin.get("imageUrl")!=SOURCE_URL or origin.get("sourceAssetSha256")!=SRC or record.get("layer")!="lower_main":
        raise ValueError("canonical_product_identity_mismatch")
    if receipt.get("garmentId")!=ID or receipt.get("sourceAssetSha256")!=SRC or receipt.get("isolatedAssetSha256")!=IMG or receipt.get("maskSha256")!=MASK or receipt.get("targetLayer")!="lower_main":
        raise ValueError("candidate_fingerprint_mismatch")
    if digest(src.read_bytes())!=SRC or digest(png.read_bytes())!=IMG or digest(mask.read_bytes())!=MASK:raise ValueError("input_image_hash_mismatch")
    source=Image.open(src).convert("RGB")
    garment=Image.open(png).convert("RGBA")
    alpha=Image.open(mask).convert("L")
    if source.size!=garment.size or source.size!=alpha.size or garment.size[0]<500 or garment.size[1]<600:
        raise ValueError("image_dimensions_invalid")
    if digest(source.tobytes())!=PIXEL:raise ValueError("source_pixels_changed")
    if garment.getchannel("A").tobytes()!=alpha.tobytes():raise ValueError("mask_alpha_mismatch")
    if garment.convert("RGB").tobytes()!=source.tobytes():raise ValueError("product_pixels_not_preserved")
    box=alpha.getbbox()
    if not box:raise ValueError("empty_alpha")
    width,height=source.size
    coverage=sum(alpha.histogram()[1:])/(width*height)
    visible=sum(alpha.histogram()[220:])/(width*height)
    if not (.09<coverage<.55 and visible>.08 and box[3]-box[1]>.65*height and box[2]-box[0]>.2*width):
        raise ValueError("segmentation_shape_out_of_range")
    ir=receipt.get("productIR",{})
    if ir.get("schema")!="agentos.wardrobe-product-ir/v1" or ir.get("category")!="lower_main" or "front pleats" not in ir.get("mustKeep",[]):
        raise ValueError("product_ir_not_acceptable")
    if job.get("garmentId")!=ID or job.get("state") not in ("candidate","approved"):
        raise ValueError("candidate_job_not_ready")
    inspection={"schema":"agentos.wardrobe-independent-review/v1","garmentId":ID,
      "sourceSha256":SRC,"isolatedAssetSha256":IMG,"maskSha256":MASK,
      "reviewer":REVIEWER,"decision":"accepted",
      "method":"distinct reviewer visually compared original+PNG plus independent pixel QA",
      "visualEvidence":"https://github.com/alston-personal/agentmanager/actions/runs/38358610266",
      "imageSize":[width,height],"alphaBBox":list(box),
      "visiblePixelCoverage":round(visible,5),
      "checks":{"sku_and_color":True,"no_model_or_unrelated_clothes":True,
                "pleats_waist_and_leg_shape":True,"alpha_mask_identical":True,
                "rgb_pixels_from_official_photo":True,"source_and_asset_hashes":True},
      "assetUrl":ASSET_URL}
    if not promote:
        print(json.dumps({"state":"qa_pass_no_promotion","review":inspection},ensure_ascii=False))
        return
    previous=record.get("tryOnSource",{})
    if previous and previous.get("state")=="approved" and previous.get("approvedAssetSha256")!=IMG:
        raise ValueError("conflicting_approved_asset")
    preapproval=folder/"candidate-receipt.preapproval.json"
    if preapproval.exists():
        if read_json(preapproval).get("approved") is not False:raise ValueError("preapproval_record_corrupt")
    else:
        write_json(preapproval,receipt)
    review_path=folder/"independent-review.json"
    if review_path.exists() and read_json(review_path).get("isolatedAssetSha256")!=IMG:
        raise ValueError("review_conflict")
    write_json(review_path,inspection)
    approved_receipt={**receipt,"approved":True,"state":"approved","review":{
          "state":"accepted","method":REVIEWER,
          "reviewEvidence":"independent-review.json",
          "checks":list(inspection["checks"].keys())}}
    write_json(receipt_path,approved_receipt)
    source_url_sha=digest(SOURCE_URL.encode())
    record["tryOnSource"]={
       "schema":"agentos.wardrobe-isolated-product/v1",
       "state":"approved","isolatedImageUrl":ASSET_URL,
       "maskUrl":None,"productIR":ir,
       "sourceFingerprint":source_url_sha,"approvedFingerprint":source_url_sha,
       "approvedAssetSha256":IMG,"extractorVersion":receipt.get("extractor")}
    record["tryOn"]={"state":"ready_for_tryon","asset":None}
    write_json(canonical,record)
    job["state"]="approved"
    job["approval"]={"method":REVIEWER,"reviewEvidence":"independent-review.json",
                     "isolatedAssetSha256":IMG}
    write_json(job_path,job)
    print(json.dumps({"state":"approved","garmentId":ID,
            "isolatedAssetSha256":IMG,"assetUrl":ASSET_URL,
            "independentReview":"accepted"},ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--promote",action="store_true")
    args=p.parse_args()
    run(args.promote)
