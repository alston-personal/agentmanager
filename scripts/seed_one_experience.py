#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.experience_store import (
    digest_set,
    experience_path,
    read_experience_set,
    seed_experience_set,
    validate_set,
)


def probe_seed(seed_path: Path) -> dict:
    incoming = validate_set(json.loads(seed_path.read_text(encoding="utf-8")))
    project_id = incoming["project_id"]
    incoming_digest = digest_set(incoming)
    target = experience_path(project_id)
    current_digest = None
    exists = target.is_file()
    if exists:
        current_digest = digest_set(read_experience_set(project_id))
    return {
        "schema": "agentos.experience-seed-probe/v1",
        "project_id": project_id,
        "exists": exists,
        "current_digest": current_digest,
        "incoming_digest": incoming_digest,
        "same_digest": current_digest == incoming_digest if current_digest is not None else False,
        "credential_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed accepted Experience into the ONE data layer")
    parser.add_argument("--seed", default="experience/agentos-core-oracle.seed.json")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    seed_path = Path(args.seed).resolve()
    probe = probe_seed(seed_path)
    print(json.dumps(probe, ensure_ascii=False, sort_keys=True))
    if args.probe_only:
        return 0
    receipt = seed_experience_set(seed_path)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
