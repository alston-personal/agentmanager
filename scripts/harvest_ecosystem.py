#!/usr/bin/env bash
#!/usr/bin/env python3
"""Ecosystem Handoff Harvester and Master Aggregator.

Collects node handoff payloads across distributed nodes and synthesizes
a master handoff snapshot in the central agent-data layer.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Ensure root import paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentos_node.inspector import NodeInspector
from agent_core import config


def aggregate_payloads(payloads: list[dict]) -> str:
    """Combine node payloads into a Markdown master handoff report."""
    now = datetime.now().isoformat()
    lines = [
        "# AgentOS Ecosystem Master Handoff",
        "",
        f"- **Aggregated At**: `{now}`",
        f"- **Total Active Nodes Repositories**: `{len(payloads)}`",
        "",
        "## Active Nodes Inventory",
        "",
        "| Device Alias | Hostname | OS | Agent Mode | Secrets | Git Commit | Status |",
        "|---|---|---|---|---|---|---|",
    ]

    for p in payloads:
        alias = p.get("device_alias", "unknown")
        hostname = p.get("hostname", "unknown")
        os_info = p.get("os", "unknown")
        mode = p.get("agent_mode", "CLIENT")
        secrets = "ISOLATED" if p.get("secrets_info", {}).get("has_secrets") else "MISSING"
        commit = p.get("git_info", {}).get("commit", "")[:8]
        status = p.get("status", "HEALTHY")

        lines.append(f"| `{alias}` | `{hostname}` | `{os_info}` | `{mode}` | `{secrets}` | `{commit}` | `{status}` |")

    lines.extend([
        "",
        "## Harvested Node Payloads",
        ""
    ])

    for p in payloads:
        lines.append(f"### Node: `{p.get('device_alias')}`")
        lines.append("```json")
        lines.append(json.dumps(p, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main():
    print("🌾 Starting AgentOS Ecosystem Handoff Harvesting...")

    # 1. Harvest local node payload
    inspector = NodeInspector()
    local_payload = inspector.harvest_payload()
    print(f" [✓] Local node harvested: [{local_payload['device_alias']}] ({local_payload['os']})")

    payloads = [local_payload]

    # 2. Check for additional node reports saved in agent-data/handoffs/nodes/
    data_root = getattr(config, "AGENT_DATA_ROOT", config.PROJECT_ROOT / "data")
    handoffs_dir = data_root / "handoffs" / "nodes"
    handoffs_dir.mkdir(parents=True, exist_ok=True)

    if handoffs_dir.exists():
        for f in handoffs_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if data.get("device_alias") != local_payload["device_alias"]:
                        payloads.append(data)
                        print(f" [✓] Remote node report loaded: [{data.get('device_alias')}]")
            except Exception as e:
                print(f" [!] Warning: Could not read node report {f}: {e}")

    # 3. Aggregate master report
    master_report = aggregate_payloads(payloads)
    today_str = datetime.now().strftime("%Y%m%d")
    output_path = data_root / "handoffs" / f"{today_str}_master_handoff.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fp:
        fp.write(master_report)

    print(f"\n✅ Master Ecosystem Handoff synthesized successfully!")
    print(f"   Target File: {output_path}")
    print(f"   Nodes Summarized: {len(payloads)}")


if __name__ == "__main__":
    main()
