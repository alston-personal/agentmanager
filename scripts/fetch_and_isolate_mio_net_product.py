#!/usr/bin/env python3
"""Download a declared NET image and run existing fail-closed garment isolation.

Only the sourceImageUrl from an existing canonical isolation job is accepted.
No arbitrary URL arguments, redirects, private hosts or automatic approval.
"""
import argparse
import ipaddress
import json
import os
import socket
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image
from run_mio_product_isolation import ROOT, run

MAX_BYTES = 12 * 1024 * 1024
IMAGE_HOSTS = {"net.wimg.tw", "s-net.wimg.tw"}
SCHEMA = "agentos.wardrobe-isolation-job/v1"

def validate_url(url):
    if not isinstance(url, str):
        raise ValueError("source URL missing")
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in IMAGE_HOSTS or u.username or u.password or u.port not in (None, 443):
        raise ValueError("unapproved NET image host")
    if not u.path or u.fragment:
        raise ValueError("invalid image URL")
    return u

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("image redirects forbidden")

def download(url, target):
    parsed = validate_url(url)
    # DNS defense in depth: reject any non-public resolution, including mixed results.
    answers = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
        raise ValueError("unsafe image host resolution")
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "MilkcatWardrobeIsolator/1.0", "Accept": "image/jpeg,image/png,image/webp"})
    with opener.open(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("image HTTP status not OK")
        if response.headers.get_content_type() not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("response is not an image")
        advertised = response.headers.get("Content-Length")
        if advertised and int(advertised) > MAX_BYTES:
            raise ValueError("image exceeds size limit")
        size = 0
        with target.open("xb") as out:
            while True:
                part = response.read(min(65536, MAX_BYTES + 1 - size))
                if not part:
                    break
                size += len(part)
                if size > MAX_BYTES:
                    raise ValueError("image exceeds size limit")
                out.write(part)
    with Image.open(target) as image:
        image.verify()
    if target.stat().st_size < 1000:
        raise ValueError("source image too small")
    return target

def run_job(garment_id):
    if not garment_id or len(garment_id) > 160 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in garment_id):
        raise ValueError("invalid garment id")
    path = ROOT / "isolation_jobs" / (garment_id + ".json")
    task = json.loads(path.read_text(encoding="utf-8"))
    if task.get("schema") != SCHEMA or task.get("garmentId") != garment_id:
        raise ValueError("isolation job mismatch")
    if task.get("state") == "approved":
        raise ValueError("approved isolation is immutable")
    url = task.get("sourceImageUrl")
    validate_url(url)
    with tempfile.TemporaryDirectory(prefix="mio-isolation-") as tmp:
        original = Path(tmp) / "source"
        download(url, original)
        receipt = run(garment_id, original)
    receipt["sourceImageUrl"] = url
    return receipt

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("garment_id")
    args = parser.parse_args()
    print(json.dumps(run_job(args.garment_id), ensure_ascii=False))
