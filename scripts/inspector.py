#!/usr/bin/env python3
"""
🔍 AgentOS Inspector Agent
===========================
驗證 Lobster Engine 執行結果的真實性。
避免模型「說做了但沒做」的假完成問題。

驗證三層：
  1. 輸出關鍵詞掃描（✅ 完成 / ⚠️ 人工介入）
  2. Git diff 檢查（有沒有實際檔案變更）
  3. 任務類型感知（程式任務 vs 文件任務 vs 分析任務）

返回碼：
  PASS    - 驗證通過，任務確實完成
  FAIL    - 驗證失敗，需重試
  BLOCKED - 需人工介入（3 次失敗 or 明確聲明需人工）
  SKIP    - 無法驗證（跳過，預設信任）
"""
import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger("Inspector")

# 任務類型分類（決定驗證嚴格度）
CODE_KEYWORDS = ["實作", "新增", "修復", "建立", "implement", "fix", "create", "add", "build", "refactor"]
DOC_KEYWORDS = ["文件", "README", "規格", "撰寫", "記錄", "document", "write", "spec", "note"]
ANALYSIS_KEYWORDS = ["分析", "研究", "調查", "報告", "evaluate", "research", "investigate", "analyze"]

# 完成信號
SUCCESS_SIGNALS = ["✅ 任務完成", "✅ task complete", "✅ done", "任務已完成", "完成了", "已完成"]
BLOCKED_SIGNALS = ["⚠️ 需要人工介入", "需要人工", "need human", "human intervention", "cannot proceed"]

InspectorResult = Literal["PASS", "FAIL", "BLOCKED", "SKIP"]


def detect_task_type(task_text: str) -> str:
    """偵測任務類型：code / doc / analysis / unknown"""
    text_lower = task_text.lower()
    if any(k in text_lower for k in CODE_KEYWORDS):
        return "code"
    if any(k in text_lower for k in DOC_KEYWORDS):
        return "doc"
    if any(k in text_lower for k in ANALYSIS_KEYWORDS):
        return "analysis"
    return "unknown"


def check_output_signals(output: str) -> tuple[bool, bool]:
    """
    掃描 Claude 輸出中的完成/阻斷信號。
    返回 (has_success, has_blocked)
    """
    output_lower = output.lower()
    has_success = any(s.lower() in output_lower for s in SUCCESS_SIGNALS)
    has_blocked = any(s.lower() in output_lower for s in BLOCKED_SIGNALS)
    return has_success, has_blocked


def check_git_diff(proj_dir: Path, min_changes: int = 1) -> tuple[bool, str]:
    """
    檢查 git 工作區有沒有未提交的變更。
    返回 (has_changes, summary_string)
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        stat = result.stdout.strip()

        # 也檢查 untracked files（新建的檔案）
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()

        has_changes = bool(stat) or bool(untracked)
        summary = stat or f"(新增 {len(untracked.splitlines())} 個未追蹤檔案)" if untracked else "(無變更)"
        return has_changes, summary

    except Exception as e:
        logger.warning(f"Git diff 失敗: {e}")
        return None, "GIT_ERROR"


def check_expected_files(proj_dir: Path, task_text: str) -> bool:
    """
    對於特定類型任務，檢查是否有對應的檔案被建立/修改。
    只做輕量啟發式判斷。
    """
    # 如果任務提到特定副檔名，檢查是否存在
    ext_patterns = {
        r"\.(py|ts|js|go|rs)\b": [".py", ".ts", ".js", ".go", ".rs"],
        r"\.(md|txt)\b": [".md", ".txt"],
        r"\.(json|yaml|yml)\b": [".json", ".yaml", ".yml"],
    }

    for pattern, exts in ext_patterns.items():
        if re.search(pattern, task_text, re.IGNORECASE):
            # 檢查最近修改的檔案
            try:
                result = subprocess.run(
                    ["find", str(proj_dir), "-newer", str(proj_dir / ".git" / "index"),
                     "-name", f"*{exts[0]}", "-not", "-path", "*/node_modules/*",
                     "-not", "-path", "*/.git/*"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.stdout.strip():
                    return True
            except Exception:
                pass

    return False  # 找不到也不能算失敗，只是提示


def inspect(
    proj_dir: Path,
    task_text: str,
    claude_output: str,
    failure_count: int = 0,
) -> tuple[InspectorResult, str]:
    """
    主驗證入口。
    
    Args:
        proj_dir: 專案目錄
        task_text: 任務描述
        claude_output: Claude 的輸出文字
        failure_count: 這個任務已失敗幾次（超過 3 次自動 BLOCKED）
    
    Returns:
        (result, reason_string)
    """
    logger.info(f"🔍 開始驗證任務: {task_text[:50]}...")

    # ── 0. 阻斷次數上限 ──
    if failure_count >= 3:
        reason = f"已連續失敗 {failure_count} 次，需人工介入"
        logger.warning(f"🚫 BLOCKED: {reason}")
        return "BLOCKED", reason

    # ── 1. 輸出關鍵詞掃描 ──
    has_success, has_blocked = check_output_signals(claude_output)

    if has_blocked:
        reason = "Claude 輸出顯示需要人工介入"
        logger.warning(f"🚫 BLOCKED: {reason}")
        return "BLOCKED", reason

    task_type = detect_task_type(task_text)
    logger.info(f"📋 任務類型: {task_type}")

    # ── 2. 分析/調查類任務 → 只看輸出信號即可 ──
    if task_type == "analysis":
        if has_success or len(claude_output) > 200:
            reason = f"分析任務，輸出長度 {len(claude_output)} 字，視為完成"
            logger.info(f"✅ PASS: {reason}")
            return "PASS", reason
        else:
            reason = "分析任務但輸出過短，可能未完成"
            logger.warning(f"⚠️ FAIL: {reason}")
            return "FAIL", reason

    # ── 3. Git diff 檢查（適用程式和文件任務）──
    if not proj_dir.exists():
        logger.warning(f"專案目錄不存在: {proj_dir}，跳過驗證")
        return "SKIP", "PROJECT_DIR_NOT_FOUND"

    # 檢查是否是 git repo
    git_dir = proj_dir / ".git"
    if not git_dir.exists():
        if has_success:
            return "PASS", "非 git repo，依賴輸出信號通過"
        return "SKIP", "非 git repo 且無明確成功信號"

    has_changes, diff_summary = check_git_diff(proj_dir)

    # ── 4. 程式任務：必須有檔案變更 ──
    if task_type == "code":
        if has_changes:
            reason = f"程式任務驗證通過，變更摘要: {diff_summary[:100]}"
            logger.info(f"✅ PASS: {reason}")
            return "PASS", reason
        elif has_success:
            # Claude 說完成但沒有 diff → 可疑，降級為 FAIL
            reason = f"Claude 聲稱完成但無檔案變更（diff: {diff_summary}）"
            logger.warning(f"⚠️ FAIL (假完成偵測): {reason}")
            return "FAIL", reason
        else:
            reason = f"程式任務無檔案變更且無成功信號（diff: {diff_summary}）"
            logger.warning(f"⚠️ FAIL: {reason}")
            return "FAIL", reason

    # ── 5. 文件任務：有 diff 或有成功信號都算通過 ──
    if task_type == "doc":
        if has_changes or has_success:
            reason = f"文件任務通過（{'有檔案變更' if has_changes else '輸出信號通過'}）"
            logger.info(f"✅ PASS: {reason}")
            return "PASS", reason
        else:
            reason = "文件任務無變更且無成功信號"
            logger.warning(f"⚠️ FAIL: {reason}")
            return "FAIL", reason

    # ── 6. 未知類型：寬鬆模式（有任何信號就通過）──
    if has_success or has_changes:
        reason = f"未知類型任務，寬鬆通過（success_signal={has_success}, has_diff={has_changes}）"
        logger.info(f"✅ PASS (寬鬆): {reason}")
        return "PASS", reason

    # 完全沒有任何信號 → FAIL
    reason = f"未知類型任務，無任何完成信號（output len={len(claude_output)}）"
    logger.warning(f"⚠️ FAIL: {reason}")
    return "FAIL", reason


if __name__ == "__main__":
    # 快速測試
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    proj = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/ubuntu/youtube-ai-manager")
    task = sys.argv[2] if len(sys.argv) > 2 else "實作新功能測試"
    output = sys.argv[3] if len(sys.argv) > 3 else "✅ 任務完成：已實作功能"

    result, reason = inspect(proj, task, output)
    print(f"\nResult: {result}")
    print(f"Reason: {reason}")
