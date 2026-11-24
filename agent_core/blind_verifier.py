#!/usr/bin/env python3
"""
AgentOS 盲審獨立驗收器 (Blind Verifier)
------------------------------------
核心鐵律：
1. 嚴禁執行者「球員兼裁判」自己驗收自己。
2. 驗收者與施工者物理隔離（不知情盲審）：
   驗收者只接收：
     - 原始驗收條件（Acceptance Criteria / Verification Command）
     - 施工前基準（Baseline）
     - 施工後目標檔案或環境狀態
   驗收者完全不聽信施工者聲稱的「我已完成」、「PASS」或任何自我回報日誌。
3. 盲審器以獨立進程執行嚴格裁決，產出不可篡改之 `blind_verification_receipt`。
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

def verify_blindly(
    worker_role: str,
    target_project: str,
    verification_command: str,
    expected_artifacts: Optional[List[str]] = None,
    timeout_sec: int = 30
) -> Dict[str, Any]:
    """
    執行盲審驗收：
    以不知情第三方裁決者的身份，獨立執行物理驗收命令並檢查交付物。
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    findings = []
    verdict = "PASS"

    # 1. 物理指令驗收 (Physical Command Execution)
    cmd_exit = -1
    cmd_stdout = ""
    cmd_stderr = ""
    if verification_command:
        try:
            cwd = Path(f"/home/ubuntu/{target_project}")
            if not cwd.exists():
                cwd = Path("/home/ubuntu/agentmanager")

            res = subprocess.run(
                verification_command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )
            cmd_exit = res.returncode
            cmd_stdout = res.stdout.strip()
            cmd_stderr = res.stderr.strip()

            if cmd_exit == 0:
                findings.append(f"✅ 盲審指令通過: `{verification_command}` (exit=0)")
            else:
                verdict = "FAIL"
                findings.append(f"❌ 盲審指令失敗: `{verification_command}` (exit={cmd_exit}) - {cmd_stderr[:120]}")
        except subprocess.TimeoutExpired:
            verdict = "FAIL"
            findings.append(f"❌ 盲審指令逾時: `{verification_command}` (超過 {timeout_sec} 秒)")
        except Exception as e:
            verdict = "FAIL"
            findings.append(f"❌ 盲審指令執行例外: {e}")
    else:
        verdict = "FAIL"
        findings.append("❌ 盲審失敗: 任務無任何可執行之物理驗收指令 (Missing Verification Command)")

    # 2. 交付物物理存在與大小檢查 (Artifact Existence Check)
    if expected_artifacts:
        for art in expected_artifacts:
            art_path = Path(art)
            if not art_path.exists():
                verdict = "FAIL"
                findings.append(f"❌ 盲審交付物缺失: 實體檔案不存在 {art_path}")
            elif art_path.stat().st_size == 0:
                verdict = "FAIL"
                findings.append(f"❌ 盲審交付物空洞: 檔案大小為 0 字元 {art_path}")
            else:
                findings.append(f"✅ 盲審交付物實體存在: {art_path.name} ({art_path.stat().st_size} bytes)")

    receipt = {
        "schema": "agentos.blind-verification-receipt/v1",
        "verifier": "independent.blind_verifier_sentinel",
        "worker_role": worker_role,
        "target_project": target_project,
        "timestamp": timestamp,
        "verdict": verdict,
        "verification_command": verification_command,
        "command_exit": cmd_exit,
        "findings": findings,
    }

    return receipt

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: blind_verifier.py <project> <verification_command>")
        sys.exit(1)
    res = verify_blindly("cli_manual", sys.argv[1], sys.argv[2])
    print(json.dumps(res, indent=2, ensure_ascii=False))
    sys.exit(0 if res["verdict"] == "PASS" else 1)
