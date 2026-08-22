#!/usr/bin/env python3
"""Emit a read-only AgentOS Node capability manifest as JSON."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from agentos_node.capability_discovery import DiscoveryContext, discover_linux_capabilities


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--realm-id", required=True)
    parser.add_argument("--profile", default="edge")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = discover_linux_capabilities(
        DiscoveryContext(
            realm_id=args.realm_id,
            node_id=args.node_id,
            observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            profile=args.profile,
        )
    )
    payload = asdict(manifest)
    payload["manifest_id"] = manifest.manifest_id
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(manifest.manifest_id)
    print(f"capability_count={len(manifest.capabilities)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
