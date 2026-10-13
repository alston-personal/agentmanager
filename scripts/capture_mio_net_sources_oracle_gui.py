#!/usr/bin/env python3
"""Fetch NET product source candidates via the existing Oracle GUI Worker CDP.

Uses a NEW isolated browser context (never the Threads/Google account tabs).
This is read-only with respect to the wardrobe registry: immutable source
snapshots and audit receipts only; an independently checked image is required
before promotion or segmentation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit

ALLOWED_SHOPS = {"www.net-fashion.net", "m.net-fashion.net"}
ALLOWED_IMAGES = {"s-net.wimg.tw", "net.wimg.tw"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024
ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))) / "projects/dressup-simulator"


def image_candidates(html: str, document_urls: list[str], shop_url: str) -> list[str]:
    # Read actual browser DOM + image attributes, not guessed CDN path formats.
    raw = list(document_urls)
    raw += re.findall(r"(?:https?:)?//(?:s-net|net)\.wimg\.tw/[^\s\"'<>\\]+", html, flags=re.I)
    result: list[str] = []
    for token in raw:
        if not isinstance(token, str):
            continue
        candidate = urljoin(shop_url, token.replace("&amp;", "&"))
        parsed = urlsplit(candidate)
        if (parsed.scheme == "https" and parsed.hostname in ALLOWED_IMAGES
                and parsed.username is None and parsed.password is None
                and parsed.fragment == "" and candidate not in result):
            result.append(candidate)
    return result[:100]


def match_source(url: str, row: dict) -> bool:
    path = urlsplit(url).path.lower()
    option = str(row["optionId"])
    product = str(row["productId"])
    color = row.get("variantCode")
    # Distinguish a variant-specific product photo from unrelated page chrome.
    return (bool(re.search(r"(?<!\d)" + re.escape(option) + r"(?!\d)", path))
            or (bool(color) and re.search(
                r"(?<!\d)" + re.escape(product) + r"[-_]" + re.escape(str(color)) + r"(?!\d)", path) is not None))


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temp = Path(f.name)
    os.chmod(temp, 0o600)
    temp.replace(path)


def process(page, ctx, row: dict) -> dict:
    garment_id = row["garmentId"]
    result = {"schema": "agentos.mio-net-source-capture/v1",
              "garmentId": garment_id, "productId": row["productId"],
              "optionId": row["optionId"], "variantCode": row.get("variantCode"),
              "productUrl": row["productUrl"], "status": "unresolved",
              "approved": False, "candidateUrls": []}
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", garment_id):
        raise ValueError("unsafe garment ID")
    p = urlsplit(row["productUrl"])
    if p.scheme != "https" or p.hostname not in ALLOWED_SHOPS or not p.path.startswith("/product/"):
        raise ValueError("untrusted NET product URL")
    try:
        res = page.goto(row["productUrl"], wait_until="domcontentloaded", timeout=22000)
        status = res.status if res else None
        result["httpStatus"] = status
        if status != 200:
            result["status"] = "browser_http_unavailable"
            return result
        body = page.content()
        # Extract only a bounded source body; verify the expected SKU is
        # displayed on the product page, not merely in a candidate image URL.
        if not re.search(r"商品編號\s*[:：]?\s*" + re.escape(str(row["productId"])), body):
            result["status"] = "product_identity_not_verified"
            return result
        found = page.evaluate("""() => {
          const values=[];
          document.querySelectorAll('meta[property="og:image"],meta[name="twitter:image"]').forEach(el=>values.push(el.content));
          document.querySelectorAll('img').forEach(el=>{
            for(const key of ['src','data-src','data-original','data-lazy-src','srcset'])
              if(el.getAttribute(key)) values.push(el.getAttribute(key));
            if(el.currentSrc) values.push(el.currentSrc);
          });
          return values;
        }""")
        candidates = image_candidates(body, found, page.url)
        matched = [url for url in candidates if match_source(url, row)]
        result["candidateUrls"] = matched[:15]
        if not matched:
            result["status"] = "no_variant_matched_image"
            return result
        for url in matched:
            try:
                response = ctx.request.get(url, timeout=15000, max_redirects=0)
                ctype = (response.headers.get("content-type") or "").split(";")[0].strip()
                if response.status != 200 or ctype not in ("image/jpeg", "image/png", "image/webp"):
                    continue
                data = response.body()
                if len(data) < 1000 or len(data) > MAX_IMAGE_BYTES:
                    continue
                sha = hashlib.sha256(data).hexdigest()
                ext = {"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[ctype]
                directory = ROOT / "source_sync_candidates" / garment_id / sha
                directory.mkdir(parents=True, exist_ok=True)
                source = directory / ("original" + ext)
                if source.exists():
                    if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != sha:
                        raise ValueError("immutable source mismatch")
                else:
                    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as f:
                        f.write(data)
                        staged = Path(f.name)
                    os.chmod(staged, 0o600)
                    staged.replace(source)
                result.update(status="source_candidate_captured",
                              sourceAssetSha256=sha,sourceUrl=url,
                              contentType=ctype,sourceBytes=len(data),
                              variantIdentityVerified=bool(row.get("variantCode")),
                              targetIsolationApproved=False)
                return result
            except Exception as exc:
                result["downloadErrorType"] = type(exc).__name__
        result["status"] = "variant_image_download_failed"
    except Exception as exc:
        result["status"] = "browser_navigation_failed"
        result["errorType"] = type(exc).__name__
    return result


def run(manifest: Path, cdp: str) -> int:
    from playwright.sync_api import sync_playwright
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema") != "agentos.mio-net-source-backfill/v1":
        raise ValueError("manifest schema mismatch")
    items = data.get("items")
    if not isinstance(items,list) or len(items)>25:
        raise ValueError("invalid manifest size")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp, timeout=10000)
        context = browser.new_context(locale="zh-TW", viewport={"width":1280,"height":900})
        try:
            page = context.new_page()
            for row in items:
                receipt = process(page, context, row)
                atomic_json(ROOT / "source_sync_attempts" / (row["garmentId"] + ".json"), receipt)
                print(json.dumps({key:receipt.get(key) for key in
                      ("garmentId","status","httpStatus","variantIdentityVerified","sourceAssetSha256")},
                      ensure_ascii=False),flush=True)
            page.close()
        finally:
            context.close()   # Only close the temporary isolated context.
            # Never call browser.close() on the shared CDP server: preserve account tabs.
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args()
    raise SystemExit(run(args.manifest, args.cdp))
