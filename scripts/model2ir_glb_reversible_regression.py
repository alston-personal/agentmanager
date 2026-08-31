#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from model2ir import extract_ir, ir_digest, save_reversible_glb, verify_glb_container_preservation


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    source = Path(args.asset).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    output = out / ("reversible" + source.suffix.lower())

    source_hash_before = sha256_file(source)
    canonical_ir = {
        "schema": "character-ir/v0.9-regression-fixture",
        "truth_status": "confirmed",
        "identity": {"archetype": "humanoid", "locked": True},
        "provenance": {
            "purpose": "model2ir binary-container preservation regression",
            "source_asset_sha256": source_hash_before,
            "note": "This fixture tests reversible carriage only; it is not inferred from the source model.",
        },
        "unresolved": [],
    }

    save_reversible_glb(source, canonical_ir, output)
    source_hash_after = sha256_file(source)
    preservation = verify_glb_container_preservation(source, output, canonical_ir)
    recovered = extract_ir(output)

    assert source_hash_after == source_hash_before
    assert preservation["lossless_reversible"] is True
    assert preservation["container"]["non_json_chunks_exact"] is True
    assert preservation["container"]["json_expected"] is True
    assert preservation["container"]["relocatable"] is True
    assert recovered["reversibility"]["lossless"] is True
    assert recovered["canonical_ir"] == canonical_ir
    assert recovered["canonical_ir_digest"] == ir_digest(canonical_ir)

    report = {
        "schema": "model2ir-glb-reversible-regression/v0.9",
        "source": {
            "path": source.name,
            "sha256_before": source_hash_before,
            "sha256_after": source_hash_after,
            "bytes": source.stat().st_size,
        },
        "output": {
            "path": output.name,
            "sha256": sha256_file(output),
            "bytes": output.stat().st_size,
        },
        "canonical_ir_digest": ir_digest(canonical_ir),
        "preservation": preservation,
        "gate": {
            "source_unchanged": source_hash_before == source_hash_after,
            "canonical_ir_exact": recovered["canonical_ir"] == canonical_ir,
            "non_json_chunks_exact": preservation["container"]["non_json_chunks_exact"],
            "relocatable_source": preservation["container"]["relocatable"],
            "status": "PASS",
        },
    }
    (out / "canonical-ir.json").write_text(
        json.dumps(canonical_ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "source": source.name,
                "non_json_chunks": preservation["container"]["non_json_chunk_count"],
                "canonical_ir_digest": ir_digest(canonical_ir),
            }
        )
    )


if __name__ == "__main__":
    main()
