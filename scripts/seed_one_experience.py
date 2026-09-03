#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.experience_store import seed_experience_set


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed accepted Experience IR into the ONE data layer")
    parser.add_argument("--seed", default="experience/agentos-core-oracle.seed.json")
    parser.add_argument(
        "--migrate-from",
        default="experience/agentos-core-oracle.seed.v0.json",
        help="approved legacy seed used only to verify a fail-closed v0 -> v1 migration",
    )
    args = parser.parse_args()
    migrate_from = Path(args.migrate_from).resolve() if args.migrate_from else None
    receipt = seed_experience_set(
        Path(args.seed).resolve(),
        migrate_from=migrate_from,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
