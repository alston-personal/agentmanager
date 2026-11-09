"""
👑 AgentOS Rhea Role Steward Seal & Tamper-Proof Infrastructure
(瑞亞角色神殿密碼學封印與防篡改基礎設施)
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = REPO_ROOT / ".agent" / "roles" / "registry.yaml"
AGENT_DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
SEAL_DIR = AGENT_DATA_ROOT / "governance" / "role_steward"
SEAL_PATH = SEAL_DIR / "seal.json"


def compute_sha256(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"Missing file: {file_path}")
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def load_seal(seal_path: Path = SEAL_PATH) -> dict[str, Any] | None:
    if not seal_path.exists():
        return None
    try:
        return json.loads(seal_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def lock_file(file_path: Path) -> None:
    """將檔案設為唯讀 (444)，防範 IDE / Agent 隨意存檔修改。"""
    if file_path.exists():
        os.chmod(file_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def unlock_file(file_path: Path) -> None:
    """暫時解除唯讀鎖 (644)，供授權維護或瑞亞審批流程使用。"""
    if file_path.exists():
        os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def verify_seal(
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    seal_path: Path = SEAL_PATH,
    raise_on_error: bool = False,
) -> bool:
    """驗證當前磁碟上的角色定義是否與瑞亞蓋印的 Seal 一致。

    若被未授權修改，或封印缺失，立即告警或阻斷。
    """
    if os.environ.get("AGENTOS_BYPASS_ROLE_SEAL") == "1":
        return True

    seal = load_seal(seal_path)
    if not seal:
        msg = (
            f"❌ [Rhea] 封印缺失 (Missing Seal): {seal_path} 不存在！\n"
            f"  系統角色處於未經瑞亞審批之非法狀態。\n"
            f"  請先執行: python3 scripts/rhea_role_steward.py --seal"
        )
        if raise_on_error:
            raise RuntimeError(msg)
        print(msg, file=sys.stderr)
        return False

    current_hash = compute_sha256(registry_path)
    sealed_hash = seal.get("registry_sha256")

    if current_hash != sealed_hash:
        msg = (
            f"❌ [Rhea] 物理防篡改攔截 (Unauthorized Mutation Detected)!\n"
            f"  磁碟當前哈希: {current_hash}\n"
            f"  瑞亞審批哈希: {sealed_hash}\n"
            f"  原因: {registry_path} 已在本地被修改，但未經瑞亞審批蓋印！\n"
            f"  防線警告: 無論是否 Git Commit，系統拒絕在未授權角色狀態下運行！\n"
            f"  修復指引: 若變更合法，請執行 python3 scripts/rhea_role_steward.py --seal 取得瑞亞蓋印；\n"
            f"           若為誤改，請執行 git checkout {registry_path} 還原。"
        )
        if raise_on_error:
            raise RuntimeError(msg)
        print(msg, file=sys.stderr)
        return False

    return True
