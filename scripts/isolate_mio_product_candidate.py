#!/usr/bin/env python3
"""Conservative isolated-product candidate extraction for studio product photos.

Do not use this to isolate an item from a model's whole outfit: that requires a
target-aware segmentation backend. Outputs remain *candidate*, never approved.
"""
import argparse
import hashlib
import json
import pathlib
from collections import deque
from PIL import Image

def isolate_uniform_background(source: pathlib.Path, dest: pathlib.Path):
    img = Image.open(source).convert("RGBA")
    w,h=img.size
    if w < 100 or h < 100:
        return {"state":"needs_target_segmentation","reason":"source_too_small"}
    rgb=img.convert("RGB")
    corners=[rgb.getpixel(p) for p in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]]
    if min(min(x) for x in corners)<225 or max(max(x)-min(x) for x in corners)>22:
        return {"state":"needs_target_segmentation","reason":"nonuniform_or_busy_background"}
    background=tuple(round(sum(px[i] for px in corners)/4) for i in range(3))
    # Work at reduced resolution to cap time/memory on vendor originals.
    thumb=img.copy()
    thumb.thumbnail((512,512), Image.Resampling.LANCZOS)
    tw,th=thumb.size
    pixels=thumb.load()
    q=deque()
    visited=bytearray(tw*th)
    def idx(x,y):return y*tw+x
    for x in range(tw):
        q.append((x,0));q.append((x,th-1))
    for y in range(th):
        q.append((0,y));q.append((tw-1,y))
    def similar(r,g,b):
        return max(abs(r-background[0]),abs(g-background[1]),abs(b-background[2])) <= 32
    while q:
        x,y=q.popleft()
        i=idx(x,y)
        if visited[i]:
            continue
        visited[i]=1
        r,g,b,a=pixels[x,y]
        if not similar(r,g,b):
            continue
        pixels[x,y]=(r,g,b,0)
        if x>0:q.append((x-1,y))
        if x+1<tw:q.append((x+1,y))
        if y>0:q.append((x,y-1))
        if y+1<th:q.append((x,y+1))
    opaque=sum(1 for px in thumb.getdata() if px[3]>0)
    coverage=opaque/(tw*th)
    if coverage<0.08 or coverage>0.85:
        return {"state":"needs_target_segmentation","reason":"ambiguous_product_coverage","coverage":round(coverage,4)}
    dest.parent.mkdir(parents=True,exist_ok=True)
    mask_path = dest.with_name(dest.stem + ".mask.png")
    # Use the actual alpha channel as the reproducible isolation mask.
    # Both files are candidates and require target-aware visual verification.
    alpha = thumb.getchannel("A")
    thumb.save(dest,format="PNG")
    alpha.save(mask_path,format="PNG")
    return {
        "state":"candidate", "isolatedImagePath":str(dest),
        "maskPath":str(mask_path),
        "maskSha256":hashlib.sha256(mask_path.read_bytes()).hexdigest(),
        "sha256":hashlib.sha256(dest.read_bytes()).hexdigest(),
        "coverage":round(coverage,4),
        "note":"Background removal is not object selection. Human/semantic QC required."
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("source",type=pathlib.Path)
    parser.add_argument("dest",type=pathlib.Path)
    args=parser.parse_args()
    print(json.dumps(isolate_uniform_background(args.source,args.dest),ensure_ascii=False))

if __name__=="__main__":
    main()
