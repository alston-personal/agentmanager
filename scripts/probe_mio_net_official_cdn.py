#!/usr/bin/env python3
"""Probe exact NET SKU+color image names on the already used official NET CDN.

A successful GET plus image decode establishes the URL actually exists, not
that the garment crop is independently accepted for dress-up. No promotion.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit
from PIL import Image
import io

VALID_TYPES={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}
FORMATS=("01","02","011","012","03")
MAX_BYTES=8*1024*1024

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError("redirect_forbidden")

def probe(task):
    row,number=task
    code=row.get("variantCode")
    if not code:
        return {"garmentId":row["garmentId"],"state":"variant_unverified","sourceUrl":None}
    sku=row["productId"]
    # Only exact SKU/color pairs from the pinned inventory manifest.
    url=f"https://s-net.wimg.tw//act/{sku}-{code}-1024-{number}.jpg"
    parsed=urlsplit(url)
    assert parsed.hostname=="s-net.wimg.tw" and parsed.scheme=="https"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"image/jpeg,image/webp,image/png"})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=12) as response:
            typ=response.headers.get_content_type()
            if response.status!=200 or typ not in VALID_TYPES:
                raise ValueError("not_image_response")
            raw=response.read(MAX_BYTES+1)
            if not (1500 < len(raw) <= MAX_BYTES):
                raise ValueError("image_size_out_of_range")
            with Image.open(io.BytesIO(raw)) as img:
                img.verify()
            sha=hashlib.sha256(raw).hexdigest()
            return {"garmentId":row["garmentId"],"state":"verified_cdn_image_candidate",
                "productId":sku,"variantCode":code,"sourceUrl":url,
                "imageSha256":sha,"bytes":len(raw),"contentType":typ,
                "_data":raw,"_ext":VALID_TYPES[typ]}
    except Exception as exc:
        return {"garmentId":row["garmentId"],"state":"not_found_or_rejected",
            "probeUrl":url,"errorType":type(exc).__name__}

def run(manifest:Path,output:Path):
    o=json.loads(manifest.read_text())
    if o.get("schema")!="agentos.mio-net-source-backfill/v1":raise ValueError("schema mismatch")
    jobs=[(row,n) for row in o["items"] if row.get("variantCode") for n in FORMATS]
    output.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        rows=list(executor.map(probe,jobs))
    counts={}
    summary=[]
    for row in o["items"]:
        found=[x for x in rows if x["garmentId"]==row["garmentId"] and x["state"]=="verified_cdn_image_candidate"]
        failed=[x for x in rows if x["garmentId"]==row["garmentId"] and x["state"]=="not_found_or_rejected"]
        result={"garmentId":row["garmentId"],"productId":row["productId"],
            "variantCode":row.get("variantCode"),
            "approved":False,"sourceVerified":False,
            "state":"candidate_images_found" if found else ("variant_pending" if not row.get("variantCode") else "no_cdn_images"),
            "images":[],"checked":len(found)+len(failed)}
        for x in found:
            dest=output / row["garmentId"] / (x["imageSha256"]+"."+x["_ext"])
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(x.pop("_data"))
            x.pop("_ext")
            result["images"].append(x)
        summary.append(result)
        counts[result["state"]]=counts.get(result["state"],0)+1
        print(row["garmentId"],result["state"],len(found),flush=True)
    (output/"report.json").write_text(json.dumps({"schema":"agentos.mio-net-cdn-probe/v1",
        "counts":counts,"products":summary},ensure_ascii=False,indent=2)+"\n")
    print("mio_cdn_candidates="+str(sum(len(x["images"]) for x in summary)))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    run(a.manifest,a.output)
