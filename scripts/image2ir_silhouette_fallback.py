#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def dump(path, obj):
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", required=True)
    args=ap.parse_args()

    rgb=np.asarray(Image.open(args.image).convert("RGB"), dtype=np.float32)
    h,w,_=rgb.shape
    corners=np.concatenate([
        rgb[:max(2,h//20),:max(2,w//20)].reshape(-1,3),
        rgb[:max(2,h//20),-max(2,w//20):].reshape(-1,3),
        rgb[-max(2,h//20):,:max(2,w//20)].reshape(-1,3),
        rgb[-max(2,h//20):,-max(2,w//20):].reshape(-1,3),
    ])
    bg=np.median(corners,axis=0)
    dist=np.linalg.norm(rgb-bg,axis=2)
    mask=dist>35
    ys,xs=np.where(mask)

    probe={
        "schema":"image2ir-teacher-probe/v0.1",
        "source":"silhouette-fallback/v0.1",
        "accepted":False,
        "parts":[],
        "ir":None,
    }
    if len(xs)<max(200,int(h*w*.003)):
        probe["status_text"]="foreground silhouette insufficient"
        dump(args.out,probe); print(json.dumps({"ok":True,"accepted":False})); return

    x0,x1,y0,y1=int(xs.min()),int(xs.max()),int(ys.min()),int(ys.max())
    bw=max(1,x1-x0+1); bh=max(1,y1-y0+1); cx=(x0+x1)/2
    crop=mask[y0:y1+1,x0:x1+1]

    def occupancy(yf0,yf1,xf0,xf1):
        ya=max(0,min(bh-1,int(yf0*bh))); yb=max(ya+1,min(bh,int(yf1*bh)))
        xa=max(0,min(bw-1,int(xf0*bw))); xb=max(xa+1,min(bw,int(xf1*bw)))
        return float(crop[ya:yb,xa:xb].mean())

    # Shape evidence only. No teacher IR is read here.
    head=occupancy(0.00,0.22,0.32,0.68)>.08
    torso=occupancy(0.20,0.62,0.32,0.68)>.12
    left_arm=occupancy(0.18,0.48,0.00,0.34)>.035
    right_arm=occupancy(0.18,0.48,0.66,1.00)>.035
    left_leg=occupancy(0.55,1.00,0.20,0.49)>.055
    right_leg=occupancy(0.55,1.00,0.51,0.80)>.055

    parts=[]
    if head: parts.append("head")
    if torso: parts.append("body")
    if left_arm: parts.append("left_arm")
    if right_arm: parts.append("right_arm")
    if left_leg: parts.append("left_leg")
    if right_leg: parts.append("right_leg")

    core_hits=sum([torso,left_arm,right_arm,left_leg,right_leg])
    accepted=core_hits>=3 and torso
    coverage="full_body" if left_leg and right_leg else "upper_body"
    probe.update({
        "accepted":bool(accepted),
        "app_version":"silhouette-fallback-v0.1",
        "status_text":"silhouette body-plan accepted" if accepted else "silhouette body-plan ambiguous",
        "parts":parts,
        "evidence":{
            "background_rgb":[round(float(x),2) for x in bg],
            "foreground_fraction":round(float(mask.mean()),5),
            "bbox_px":[x0,y0,x1,y1],
            "bbox_fraction":[round(bw/w,4),round(bh/h,4)],
            "method":"background-distance + normalized regional occupancy",
        },
        "ir":{
            "schema":"character-blueprint-ir/fallback-v0.1",
            "truth_status":"candidate",
            "observed":{"pose":{"coverage":coverage},"silhouette":{"bbox_px":[x0,y0,x1,y1]}},
            "assumed":{},
        } if accepted else None,
    })
    dump(args.out,probe)
    print(json.dumps({"ok":True,"accepted":bool(accepted),"parts":parts,"coverage":coverage}))


if __name__=="__main__": main()
