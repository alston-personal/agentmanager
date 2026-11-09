#!/usr/bin/env python3
"""
👑 AgentOS Rhea Role Steward (瑞亞角色總管與神殿封印系統)

職責：
1. 作為全系統角色註冊的唯一權威閘門 (Exclusive Authority Gate)。
2. 計算 .agent/roles/registry.yaml 的密碼學封印 (Cryptographic Seal)，存於 agent-data。
3. 執行期物理防篡改：所有 Worker / Runtime 載入角色前強制比對封印，本地未審批修改即刻阻斷。
4. 編輯期物理防護：審查蓋印後自動切換至唯讀模式 (chmod 444)，防範 IDE / Agent 隨手誤寫。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.role_seal import (
    DEFAULT_REGISTRY_PATH,
    SEAL_DIR,
    SEAL_PATH,
    compute_sha256,
    load_seal,
    lock_file,
    unlock_file,
    verify_seal,
)


def apply_seal() -> dict[str, Any]:
    print("👑 [Rhea] 正在執行角色神殿審查與封印流程...")

    # 先解鎖以防需要前置調整
    unlock_file(DEFAULT_REGISTRY_PATH)

    # 1. 跑 Drift Guard 驗證憲法一致性
    from scripts.drift_guard import validate
    errors, warnings, attestation = validate()
    if errors:
        print("❌ [Rhea] 憲法漂移審查失敗，拒絕蓋印：", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        lock_file(DEFAULT_REGISTRY_PATH)
        sys.exit(1)

    # 2. 跑 Role Reality Guard 驗證實體真實度
    from scripts.role_reality_guard import check_role_reality
    reports, breaches = check_role_reality()
    if breaches:
        print("❌ [Rhea] 角色真實性守門失敗，拒絕蓋印：", file=sys.stderr)
        for b in breaches:
            print(f"  - {b}", file=sys.stderr)
        lock_file(DEFAULT_REGISTRY_PATH)
        sys.exit(1)

    # 3. 計算並寫入 Seal
    current_hash = compute_sha256(DEFAULT_REGISTRY_PATH)
    SEAL_DIR.mkdir(parents=True, exist_ok=True)

    seal_data = {
        "schema": "agentos.rhea-seal/v1",
        "steward": "governance.role_steward",
        "name": "Rhea (瑞亞 - 眾神之母)",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": current_hash,
        "active_roles_count": len([r for r in reports if "LIVE_RUNTIME" in r.get("classification", "")]),
        "status": "SEALED_APPROVED",
        "verdict": "PASS",
    }

    SEAL_PATH.write_text(json.dumps(seal_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 4. 上唯讀寫入鎖
    lock_file(DEFAULT_REGISTRY_PATH)
    print("🔒 [Rhea] 角色註冊表已上物理寫入鎖 (chmod 444 Read-Only)。")

    print(f"✨ [Rhea] 角色神殿審批通過！封印已蓋上：")
    print(f"  SHA256: {current_hash}")
    print(f"  Active Roles: {seal_data['active_roles_count']}")
    print(f"  Seal Path: {SEAL_PATH}")
    return seal_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rhea Role Steward & Pantheon Seal")
    parser.add_argument("--check", action="store_true", help="Verify current registry matches Rhea's seal")
    parser.add_argument("--seal", action="store_true", help="Audit and seal current role registry")
    parser.add_argument("--lock", action="store_true", help="Lock registry.yaml as read-only (chmod 444)")
    parser.add_argument("--unlock", action="store_true", help="Unlock registry.yaml as read-write (chmod 644)")
    args = parser.parse_args()

    if args.seal:
        apply_seal()
    elif args.lock:
        lock_file(DEFAULT_REGISTRY_PATH)
        print("🔒 [Rhea] 角色註冊表已設為唯讀。")
    elif args.unlock:
        unlock_file(DEFAULT_REGISTRY_PATH)
        print("🔓 [Rhea] 角色註冊表已解除唯讀鎖。")
    else:
        if verify_seal(raise_on_error=False):
            print("✅ [Rhea] 角色註冊表完整性校驗通過 (Seal Verified)。")
            sys.exit(0)
        else:
            sys.exit(1)
