#!/usr/bin/env python3
"""Materialize a reviewed-or-pending target polygon mask from immutable source bytes.

This is an explicit manual annotation adapter, NOT automatic segmentation or
independent quality approval. It never promotes or modifies registry records.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

def materialize(source: Path, annotation: Path, output: Path):
    payload=json.loads(annotation.read_text(encoding="utf-8"))
    if payload.get("schema")!="agentos.wardrobe-target-mask-annotation/v1":
        raise ValueError("annotation schema mismatch")
    if payload.get("quality",{}).get("approved") is True:
        raise ValueError("annotation is not approval evidence")
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=payload.get("sourceAssetSha256"):
        raise ValueError("source digest mismatch")
    with Image.open(source) as image:
        original=image.convert("RGBA")
    if list(original.size)!=payload.get("imageSize"):
        raise ValueError("image dimensions mismatch")
    polygons=payload.get("polygons")
    if not isinstance(polygons,list) or not polygons:
        raise ValueError("target polygons required")
    scale=3
    mask=Image.new("L",(original.width*scale,original.height*scale),0)
    draw=ImageDraw.Draw(mask)
    for poly in polygons:
        if len(poly)<3 or any(len(pt)!=2 or not all(isinstance(v,int) for v in pt) or not (0<=pt[0]<original.width and 0<=pt[1]<original.height) for pt in poly):
            raise ValueError("invalid target polygon")
        draw.polygon([(x*scale,y*scale) for x,y in poly],fill=255)
    mask=mask.resize(original.size,Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.9))
    candidate=original.copy()
    candidate.putalpha(mask)
    output.mkdir(parents=True,exist_ok=True)
    candidate.save(output/"garment.png")
    mask.save(output/"garment.mask.png")
    receipt={
        "schema":"agentos.wardrobe-manual-isolation-candidate/v1",
        "garmentId":payload["garmentId"],
        "sourceAssetSha256":digest,
        "extractor":"manually-guided-polygons-v1",
        "isolatedAssetSha256":hashlib.sha256((output/"garment.png").read_bytes()).hexdigest(),
        "maskSha256":hashlib.sha256((output/"garment.mask.png").read_bytes()).hexdigest(),
        "state":"needs_review",
        "approved":False,
        "knownLimitations":payload["quality"].get("knownLimitations",[])
    }
    (output/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return receipt

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    p.add_argument("annotation",type=Path)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    print(json.dumps(materialize(args.source,args.annotation,args.output),ensure_ascii=False))
