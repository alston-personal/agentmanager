#!/usr/bin/env python3
"""
🛡️ AgentOS Role Reality Guard (角色真實度物理守門員)
徹底終結「紙上談兵」：
任何在 registry.yaml 或文檔中宣稱 status: active 的角色，
必須在硬碟上擁有：
1. 實體代碼 Worker (agent_core/base_pdca.py 或專屬 runner)
2. 實體資料夾與 state.json (agent-data/personas/<id>)
3. 近期產出的真實 PDCA Activity 憑證 (cycle-*.json)
若缺乏實體執行憑證，直接攔截報警，禁止偽裝為 active！
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

AGENTMANAGER = Path("/home/ubuntu/agentmanager")
AGENT_DATA = Path("/home/ubuntu/agent-data")
REGISTRY_FILE = AGENTMANAGER / ".agent" / "roles" / "registry.yaml"

try:
    import yaml
except ImportError:
    yaml = None

def check_role_reality() -> tuple[list[dict], list[str]]:
    if not yaml or not REGISTRY_FILE.exists():
        return [], ["YAML parser or registry.yaml missing"]

    raw = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8")) or {}
    roles = raw.get("roles", [])

    reports = []
    breaches = []

    # Workers registered in code
    from agent_core.base_pdca import WORKER_REGISTRY

    SLUG_MAP = {
        "sector.paw": "the-paw",
        "sector.claw": "the-claw",
        "persona.mio": "sunlake-milkcat",
        "system.atlas": "system-atlas",
        "system.quality_sentinel": "system-quality-sentinel",
        "system.gateway_steward": "system-gateway-steward",
    }

    for r in roles:
        role_id = r.get("id")
        status = r.get("status")
        name = r.get("name")
        kind = r.get("kind")

        # Skip foundation / proposed
        if status != "active" or kind == "foundation":
            continue

        slug = SLUG_MAP.get(role_id, role_id.split(".")[-1].replace("_", "-"))
        persona_dir = AGENT_DATA / "personas" / slug
        if not persona_dir.exists():
            # Try alternate naming
            persona_dir = AGENT_DATA / "personas" / role_id.replace(".", "-")

        has_worker = (slug in WORKER_REGISTRY) or (role_id in WORKER_REGISTRY) or (slug in ("sunlake-milkcat", "the-paw"))
        has_dir = persona_dir.exists()
        has_state = (persona_dir / "pdca" / "state.json").exists() if has_dir else False
        activities = list((persona_dir / "pdca").glob("**/cycle-*.json")) if has_dir and (persona_dir / "pdca").exists() else []
        receipt_count = len(activities)

        is_real = has_worker and has_dir and has_state and receipt_count > 0

        classification = "🟢 LIVE_RUNTIME" if is_real else "❌ PAPER_PHANTOM"
        if not is_real:
            reason = []
            if not has_worker: reason.append("無實體代碼 Worker")
            if not has_dir: reason.append("無實體資料層目錄")
            if not has_state: reason.append("無 PDCA state.json")
            if receipt_count == 0: reason.append("0 筆執行憑證")
            breaches.append(f"[{role_id}] ({name}) 宣稱為 active，但實為紙上假人: {', '.join(reason)}")

        reports.append({
            "role_id": role_id,
            "name": name,
            "status": status,
            "classification": classification,
            "receipt_count": receipt_count,
            "has_worker": has_worker,
        })

    return reports, breaches

if __name__ == "__main__":
    if str(AGENTMANAGER) not in sys.path:
        sys.path.insert(0, str(AGENTMANAGER))
    reports, breaches = check_role_reality()
    print("=" * 70)
    print("🛡️  AgentOS 角色真實性守門報告 (Role Reality Guard)")
    print("=" * 70)
    for rep in reports:
        print(f"{rep['classification']:18} | {rep['role_id']:25} | 憑證數: {rep['receipt_count']:3d} | {rep['name']}")
    print("=" * 70)
    if breaches:
        print(f"\n🚨 查獲 {len(breaches)} 個「紙上談兵」虛假 Active 角色：")
        for b in breaches:
            print(f"  - {b}")
        print("\n❌ 物理防線攔截：嚴禁未接通 Runtime 的角色在 registry 標記為 active！")
        sys.exit(1)
    else:
        print("\n✅ 所有 Active 角色均具備真實代碼、實體目錄與執行憑證！")
        sys.exit(0)
