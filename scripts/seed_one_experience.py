#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.experience_store import seed_experience_set


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed accepted Experience into the ONE data layer")
    parser.add_argument("--seed", default="experience/agentos-core-oracle.seed.json")
    args = parser.parse_args()
    receipt = seed_experience_set(Path(args.seed).resolve())
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
