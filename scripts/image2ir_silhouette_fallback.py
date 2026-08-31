#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image

def dump(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('image'); ap.add_argument('--out',required=True); args=ap.parse_args()
    rgb=np.asarray(Image.open(args.image).convert('RGB'),dtype=np.float32); h,w,_=rgb.shape
    k=max(2,min(h,w)//20)
    corners=np.concatenate([rgb[:k,:k].reshape(-1,3),rgb[:k,-k:].reshape(-1,3),rgb[-k:,:k].reshape(-1,3),rgb[-k:,-k:].reshape(-1,3)])
    bg=np.median(corners,axis=0); mask=np.linalg.norm(rgb-bg,axis=2)>35; ys,xs=np.where(mask)
    probe={'schema':'image2ir-teacher-probe/v0.1','source':'silhouette-fallback/v0.1','accepted':False,'parts':[],'ir':None}
    if len(xs)<max(200,int(h*w*.003)):
        probe['status_text']='foreground silhouette insufficient'; dump(args.out,probe); return
    x0,x1,y0,y1=int(xs.min()),int(xs.max()),int(ys.min()),int(ys.max()); bw=x1-x0+1; bh=y1-y0+1; crop=mask[y0:y1+1,x0:x1+1]
    def occ(a,b,c,d):
        ya=max(0,min(bh-1,int(a*bh))); yb=max(ya+1,min(bh,int(b*bh))); xa=max(0,min(bw-1,int(c*bw))); xb=max(xa+1,min(bw,int(d*bw))); return float(crop[ya:yb,xa:xb].mean())
    head=occ(0,.22,.32,.68)>.08; torso=occ(.20,.62,.32,.68)>.12; la=occ(.18,.48,0,.34)>.035; ra=occ(.18,.48,.66,1)>.035; ll=occ(.55,1,.20,.49)>.055; rl=occ(.55,1,.51,.80)>.055
    parts=[]
    for ok,name in [(head,'head'),(torso,'body'),(la,'left_arm'),(ra,'right_arm'),(ll,'left_leg'),(rl,'right_leg')]:
        if ok: parts.append(name)
    accepted=bool(torso and sum([torso,la,ra,ll,rl])>=3); coverage='full_body' if ll and rl else 'upper_body'
    probe.update({'accepted':accepted,'app_version':'silhouette-fallback-v0.1','status_text':'silhouette body-plan accepted' if accepted else 'silhouette body-plan ambiguous','parts':parts,'ir':{'schema':'character-blueprint-ir/fallback-v0.1','truth_status':'candidate','observed':{'pose':{'coverage':coverage},'silhouette':{'bbox_px':[x0,y0,x1,y1]}},'assumed':{}} if accepted else None})
    dump(args.out,probe)
if __name__=='__main__': main()
