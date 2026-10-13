#!/usr/bin/env python3
"""Run the existing conservative garment candidate extractor against a local source.

No network or approval side effects. Atomic candidate receipt; source and prior
approved artifact remain untouched. Designed for Oracle staging/backfill.
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from isolate_mio_product_candidate import isolate_uniform_background
from mio_isolation_candidate_receipt import candidate_receipt

ROOT = Path(os.environ.get("AGENT_DATA_ROOT", str(Path.home() / "agent-data"))) / "projects/dressup-simulator"

def run(garment_id: str, source: Path):
    if not garment_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in garment_id) or len(garment_id)>160:
        raise ValueError("invalid garment ID")
    task_file = ROOT / "isolation_jobs" / (garment_id + ".json")
    task = json.loads(task_file.read_text(encoding="utf-8"))
    if task.get("schema") != "agentos.wardrobe-isolation-job/v1" or task.get("garmentId") != garment_id:
        raise ValueError("isolation job mismatch")
    if task.get("state") == "approved":
        raise ValueError("approved isolation is immutable")
    if not source.is_file() or source.is_symlink():
        raise ValueError("source image missing or unsafe")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    target = ROOT / "isolation_candidates" / garment_id / source_sha
    # Keep a byte-identical, content-addressed snapshot of the source. Never
    # overwrite an existing digest path: detect corruption instead.
    source_store = ROOT / "source_images" / source_sha
    source_store.mkdir(parents=True, exist_ok=True)
    source_snapshot = source_store / "original"
    if source_snapshot.exists():
        if source_snapshot.is_symlink() or hashlib.sha256(source_snapshot.read_bytes()).hexdigest() != source_sha:
            raise ValueError("source snapshot digest mismatch")
    else:
        staged = source_store / ("original." + str(os.getpid()) + ".tmp")
        try:
            shutil.copyfile(source, staged)
            if hashlib.sha256(staged.read_bytes()).hexdigest() != source_sha:
                raise ValueError("source changed during snapshot")
            os.replace(staged, source_snapshot)
        finally:
            staged.unlink(missing_ok=True)
    destination = target / "garment.png"
    result = isolate_uniform_background(source_snapshot, destination)
    receipt = candidate_receipt(
        garment_id=garment_id,
        target_layer=task["targetLayer"],
        source_fingerprint=task["sourceFingerprint"],
        isolated_image=destination if result["state"] == "candidate" else None,
        mask=Path(result["maskPath"]) if result["state"] == "candidate" else None,
        attributes={"productName": task.get("productName", "")},
        must_keep=["product identity", "color", "cut", "texture"],
        extraction_backend="uniform-background-v1",
        target_match_evidence={"status":"unverified", "sourceAssetSha256":source_sha},
    )
    receipt["extractorOutcome"] = result["state"]
    receipt["sourceAssetSha256"] = source_sha
    receipt["sourceSnapshot"] = str(source_snapshot)
    receipt["approved"] = False
    target.mkdir(parents=True, exist_ok=True)
    receipt_file = target / "candidate-receipt.json"
    temp = receipt_file.with_suffix(".json.tmp")
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, receipt_file)
    return receipt

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("garment_id")
    p.add_argument("local_source_image", type=Path)
    a = p.parse_args()
    print(json.dumps(run(a.garment_id, a.local_source_image), ensure_ascii=False))
