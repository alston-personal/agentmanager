#!/usr/bin/env python3
import json
import sys
import time

sys.path.insert(0, "/home/ubuntu/.local/share/agentos/runtime-vnext")
from agentos_node.antigravity_relay import AntigravityRelayClient

client = AntigravityRelayClient("/home/ubuntu/agent-data/runtime/antigravity-relay")
capsule = client.submit(
    project_id="realm-readiness-live-smoke",
    canonical_ir={"goal": "Verify only the governed AgentOS Antigravity relay boundary."},
    instruction="Return exactly AGENTOS_RELAY_SMOKE_PASS. Do not modify files, repositories, services, or system state.",
    workspace="/home/ubuntu/agentmanager",
)
print("capsule_id=" + capsule["capsule_id"])

for _ in range(90):
    receipt = client.receipt(capsule["capsule_id"])
    if receipt:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        if not receipt.get("ok"):
            raise SystemExit("FAIL: relay receipt failed")
        encoded = json.dumps(receipt, ensure_ascii=False)
        if "PermissionError" in encoded or "Permission denied" in encoded:
            raise SystemExit("FAIL: cross-user permission regression")
        if "AGENTOS_RELAY_SMOKE_PASS" not in str(receipt.get("stdout") or ""):
            raise SystemExit("FAIL: missing smoke marker")
        print("cross_user_antigravity_relay=PASS")
        raise SystemExit(0)
    time.sleep(2)

raise SystemExit("FAIL: relay smoke receipt timeout")
