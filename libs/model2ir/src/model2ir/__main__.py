from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import (
    audit_asset,
    diff_ir,
    extract_ir,
    reconcile_ir,
    save_reversible_glb,
    stabilize_external_ir,
    verify_glb_container_preservation,
)


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="model2ir",
        description="Extract, stabilize, and reversibly carry Canonical Character IR in 3D assets.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="Extract the full Model2IR evidence envelope from GLB/glTF/VRM.")
    p.add_argument("asset")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("stabilize", help="Project a 3D asset to stabilized Canonical Character IR candidate/truth.")
    p.add_argument("asset")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("audit", help="Repeat extraction/stabilization and report deterministic admission status.")
    p.add_argument("asset")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--repeats", type=int, default=3)

    p = sub.add_parser("diff", help="Compare two IR JSON documents.")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("reconcile", help="Reconcile image-derived IR with model-derived IR evidence.")
    p.add_argument("image_ir")
    p.add_argument("model_ir")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser(
        "embed-ir",
        help="Embed Canonical Character IR into a self-contained GLB/VRM while preserving non-JSON chunks byte-for-byte.",
    )
    p.add_argument("asset", help="Source .glb or .vrm. The source is never modified in place.")
    p.add_argument("canonical_ir", help="Canonical Character IR JSON to embed.")
    p.add_argument("-o", "--output", required=True, help="New .glb or .vrm output path.")
    p.add_argument("--report", help="Optional JSON preservation report path.")

    return ap


def main() -> None:
    args = build_parser().parse_args()

    if args.cmd == "embed-ir":
        canonical_ir = load_json(args.canonical_ir)
        save_reversible_glb(args.asset, canonical_ir, args.output)
        report = verify_glb_container_preservation(args.asset, args.output, canonical_ir)
        if args.report:
            write_json(args.report, report)
        print(
            json.dumps(
                {
                    "ok": report["lossless_reversible"],
                    "schema": report["schema"],
                    "output": args.output,
                    "report": args.report,
                    "canonical_ir_lossless": report["canonical_ir"]["lossless"],
                    "non_json_chunks_exact": report["container"]["non_json_chunks_exact"],
                }
            )
        )
        return

    if args.cmd == "extract":
        out = extract_ir(args.asset)
    elif args.cmd == "stabilize":
        out = stabilize_external_ir(extract_ir(args.asset))
    elif args.cmd == "audit":
        if args.repeats < 1:
            raise SystemExit("--repeats must be >= 1")
        out = audit_asset(args.asset, repeats=args.repeats)
    elif args.cmd == "diff":
        out = diff_ir(load_json(args.a), load_json(args.b))
    elif args.cmd == "reconcile":
        out = reconcile_ir(load_json(args.image_ir), load_json(args.model_ir))
    else:  # pragma: no cover - argparse owns command admission.
        raise AssertionError(args.cmd)

    write_json(args.output, out)
    print(json.dumps({"ok": True, "schema": out.get("schema"), "output": args.output}))


if __name__ == "__main__":
    main()
