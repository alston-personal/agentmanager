from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import audit_asset, diff_ir, extract_ir, reconcile_ir, stabilize_external_ir


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="model2ir",
        description="Extract and stabilize evidence-preserving Canonical Character IR from 3D assets.",
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

    return ap


def main() -> None:
    args = build_parser().parse_args()

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
