#!/usr/bin/env python3
"""Generate deterministic controlled-track LCCB baseline results as JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.lccb_baselines import run_controlled_baselines
from research.lccb_synthetic import DEFAULT_SEED, generate_pack


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--events", type=int, default=1000)
    p.add_argument("--output", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    pack = generate_pack(seed=args.seed, event_count=args.events)
    result = run_controlled_baselines(pack)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
