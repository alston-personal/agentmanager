#!/usr/bin/env python3
"""Resolve safe garment-isolation candidates to a target-specific review receipt.

This is a staging adapter, not an autonomous vision segmenter. It never approves
isolated assets based only on background removal or human-provided assertions.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "agentos.wardrobe-isolation-candidate/v1"
IR_SCHEMA = "agentos.wardrobe-product-ir/v1"


def candidate_receipt(
    *,
    garment_id: str,
    target_layer: str,
    source_fingerprint: str,
    isolated_image: Path | None,
    mask: Path | None,
    attributes: dict[str, Any] | None,
    must_keep: list[str] | None,
    extraction_backend: str,
    target_match_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = str(source_fingerprint)
    if len(source) != 64 or any(ch not in "0123456789abcdef" for ch in source):
        raise ValueError("invalid source fingerprint")
    if not target_layer or not garment_id:
        raise ValueError("target layer and garment ID required")
    visual_ok = isolated_image is not None and isolated_image.is_file() and isolated_image.stat().st_size > 1000
    mask_ok = mask is not None and mask.is_file() and mask.stat().st_size > 100
    evidence = target_match_evidence if isinstance(target_match_evidence, dict) else {}
    # An extraction backend can supply candidate data, but it is not itself the
    # reviewer. Independent evidence must be supplied by a later verifier.
    state = "candidate" if visual_ok and mask_ok and attributes and must_keep else "needs_review"
    return {
        "schema": SCHEMA,
        "garmentId": garment_id,
        "targetLayer": target_layer,
        "sourceFingerprint": source,
        "state": state,
        "isolatedAsset": str(isolated_image) if visual_ok else None,
        "maskAsset": str(mask) if mask_ok else None,
        "isolatedAssetSha256": hashlib.sha256(isolated_image.read_bytes()).hexdigest() if visual_ok else None,
        "productIR": {
            "schema": IR_SCHEMA,
            "category": target_layer,
            "attributes": attributes or {},
            "mustKeep": must_keep or [],
        },
        "extractor": extraction_backend,
        "targetMatchEvidence": evidence,
        "approved": False,
        "review": {
            "state": "pending",
            "checks": ["single_target_object", "target_layer_match", "no_other_clothing", "features_preserved"],
        },
    }
