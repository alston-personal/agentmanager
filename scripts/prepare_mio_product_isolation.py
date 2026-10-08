#!/usr/bin/env python3
"""Create a traceable product-isolation candidate without silently approving it.

Usage: python3 scripts/prepare_mio_product_isolation.py GARMENT_ID
This uses the existing canonical product photo and builds an extraction task.
An extractor must produce a single-item image + mask + product IR; only
a separate quality review may promote it. Original source remains immutable.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
from datetime import datetime, timezone

ROOT = pathlib.Path(os.environ.get("AGENT_DATA_ROOT", str(pathlib.Path.home() / "agent-data"))) / "projects/dressup-simulator"
GARMENTS = ROOT / "garments"
TASKS = ROOT / "isolation_jobs"
SCHEMA = "agentos.wardrobe-isolation-job/v1"


def find_garment(garment_id):
    for folder in ("imported", "seeded"):
        base = GARMENTS / folder
        for p in base.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if str(data.get("garmentId") or data.get("garment_id") or "") == garment_id:
                return p, data
    raise FileNotFoundError(f"garment not found: {garment_id}")


def image_url(record):
    source = record.get("source") or {}
    return (source.get("imageUrl") or source.get("officialVisualUrl")
            or next((row.get("url") for row in record.get("official_visuals", []) if row.get("url")), None)
            or record.get("thumbnailUrl"))


def build_task(garment_id):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", garment_id):
        raise ValueError("invalid garment id")
    path, row = find_garment(garment_id)
    url = image_url(row)
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("no secure product reference URL")
    fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
    task_path = TASKS / (garment_id + ".json")
    if task_path.exists():
        current = json.loads(task_path.read_text(encoding="utf-8"))
        if current.get("sourceFingerprint") == fingerprint and current.get("state") in {"pending", "extracting", "candidate", "approved"}:
            return current
    task = {
        "schema": SCHEMA, "garmentId": garment_id,
        "sourceRecord": str(path.relative_to(ROOT)),
        "sourceImageUrl": url, "sourceFingerprint": fingerprint,
        "targetLayer": str(row.get("layer") or row.get("slot") or ""),
        "productName": str(row.get("name") or garment_id),
        "state": "pending",
        "requirements": {
            "singleTargetObject": True,
            "removeOtherGarments": True,
            "retainExactColorCutTextureHardware": True,
            "isolatedImageMustBeVerified": True,
            "productIRMustBeVerified": True
        },
        "isolatedImageUrl": None, "maskUrl": None, "productIR": None,
        "approval": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    TASKS.mkdir(parents=True, exist_ok=True)
    temp = task_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, task_path)
    return task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("garment_id")
    args = parser.parse_args()
    print(json.dumps(build_task(args.garment_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
