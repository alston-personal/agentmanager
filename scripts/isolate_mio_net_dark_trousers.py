#!/usr/bin/env python3
"""Target-specific NET dark trousers isolation using immutable vendor source pixels.

For SKU 31234 color 014 only. Never applied to model shots, pale garments,
other products, or other variations. Produces candidate alpha PNG + mask and
independent-review-needed receipt. It cannot grant try-on approval.
"""
import argparse,hashlib,io,json,re
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

PRODUCT="net-31234-product-689961"
EXPECTED_PIXEL_SHA="06a3aa8736af3dac238775a8c08ab90ce0fb9f5f8f5fa7ead0cdfd6d60d80ba9"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def isolate(source:Path,output:Path,source_sha:str):
    if not re.fullmatch("[a-f0-9]{64}",source_sha):
        raise ValueError("invalid source hash")
    raw=source.read_bytes()
    if sha(raw)!=source_sha:
        raise ValueError("source_asset_digest_mismatch")
    rgb_img=Image.open(io.BytesIO(raw)).convert("RGB")
    if sha(rgb_img.tobytes())!=EXPECTED_PIXEL_SHA:
        raise ValueError("source_pixels_not_canonical")
    w,h=rgb_img.size
    if w<500 or h<600 or max(w,h)>4000:
        raise ValueError("unexpected source dimensions")
    src=np.asarray(rgb_img,dtype=np.uint8)
    corner=[src[0,0],src[-1,0],src[0,-1],src[-1,-1]]
    if any(int(v.min())<245 for v in corner):
        raise ValueError("nonwhite_background_requires_target_segmentation")
    delta=255-src.astype("int16").min(axis=2)
    binary=np.uint8(delta>28)
    num,labels,stats,_=cv2.connectedComponentsWithStats(binary,8)
    if num<2:raise ValueError("foreground_not_found")
    largest=max(range(1,num),key=lambda j:stats[j,cv2.CC_STAT_AREA])
    left,top,bw,bh,area=map(int,stats[largest])
    coverage=area/(w*h)
    if not (.08<coverage<.5 and .1*w<left<.6*w and .05*h<top<.5*h and bh>.55*h):
        raise ValueError("source_not_matching_tall_single_packshot")
    body=np.uint8(labels==largest)
    band=cv2.dilate(body,np.ones((3,3),np.uint8),iterations=2)
    alpha=(np.clip((delta-6)/32,0,1)*255*band).clip(0,255).astype(np.uint8)
    rgba=np.dstack((src,alpha))
    output.mkdir(parents=True,exist_ok=True)
    garment=output/"garment.png"
    mask=output/"garment.mask.png"
    Image.fromarray(rgba,"RGBA").save(garment)
    Image.fromarray(alpha,"L").save(mask)
    row={"schema":"agentos.wardrobe-isolation-candidate/v1",
         "garmentId":PRODUCT,"targetLayer":"lower_main",
         "sourceAssetSha256":source_sha,
         "sourcePixelSha256":sha(rgb_img.tobytes()),
         "state":"candidate","approved":False,
         "extractor":"net-dark-trousers-exact-sku-v1",
         "extractorOutcome":"candidate",
         "isolatedAssetSha256":sha(garment.read_bytes()),
         "maskSha256":sha(mask.read_bytes()),
         "productIR":{
           "schema":"agentos.wardrobe-product-ir/v1",
           "category":"lower_main",
           "attributes":{"productName":"打褶後鬆緊長褲","variant":"014 深灰",
                         "color":"深灰","silhouette":"錐形褲管",
                         "sourceProvenance":"NET official SKU/color exact pixels"},
           "mustKeep":["front pleats","elasticated back waistband","tapered trouser legs",
                       "source color and texture"]},
         "review":{"state":"pending","checks":["exact_sku_variant","single_target_object",
                  "no_model_or_other_clothing","features_preserved","alpha_edges"]},
         "candidateMetrics":{"foregroundCoverage":round(coverage,4),"bbox":[left,top,bw,bh]},
         "note":"Only a candidate. The isolator is not the independent quality reviewer."}
    (output/"candidate-receipt.json").write_text(json.dumps(row,ensure_ascii=False,indent=2)+"\n")
    return row

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--source-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(isolate(a.source,a.output,a.source_sha256),ensure_ascii=False))
