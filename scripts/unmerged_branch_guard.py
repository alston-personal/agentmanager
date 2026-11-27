#!/usr/bin/env python3
"""AgentOS Unmerged Branch Convergence Guard.

依據身心合一與分散式體系治理守則：
嚴禁「口頭宣稱版本統一，但背後仍留有長期未合併孤島分支」之虛假對齊。
本守衛自動掃描本地與遠端追蹤之未合併分支，若存在超過保留天數（預設 14 天）且有代碼差異之外野特性分支，
立即輸出警告或裁定 FAIL 阻斷，強制要求建立 PR 收斂或執行歸檔刪除。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set


# 允許保留的基礎主線或維護分支
DEFAULT_ALLOWLIST = {
    "main",
    "master",
    "core/integration",
}


def _run_git(args: List[str], cwd: Path) -> str:
    res = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def get_unmerged_branches(cwd: Path, base_branch: str = "main") -> List[str]:
    """取得相對於 base_branch 尚未合併的所有分支."""
    try:
        raw = _run_git(["branch", "-a", "--no-merged", base_branch], cwd)
        branches = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # 清理標記與指標
            if line.startswith("*"):
                line = line[1:].strip()
            if " -> " in line:
                continue
            branches.append(line)
        return branches
    except Exception as e:
        print(f"Error checking unmerged branches: {e}", file=sys.stderr)
        return []


def inspect_branch_drift(branch: str, cwd: Path, base_branch: str = "main") -> Dict[str, Any]:
    """檢查特定分支與 base_branch 的差異與最後提交時間."""
    try:
        commit_hash = _run_git(["rev-parse", branch], cwd)
        author_date = _run_git(["show", "-s", "--format=%cI", commit_hash], cwd)
        subject = _run_git(["show", "-s", "--format=%s", commit_hash], cwd)
        
        # 統計相較於 base_branch 的差異檔案數
        diff_stat = _run_git(["diff", f"{base_branch}...{branch}", "--stat"], cwd)
        has_changes = bool(diff_stat.strip())

        dt = datetime.fromisoformat(author_date)
        now = datetime.now(timezone.utc)
        days_idle = (now - dt).total_seconds() / 86400.0

        return {
            "branch": branch,
            "commit": commit_hash[:8],
            "last_commit_date": author_date,
            "days_idle": round(days_idle, 1),
            "subject": subject,
            "has_changes": has_changes,
        }
    except Exception as e:
        return {
            "branch": branch,
            "error": str(e),
            "has_changes": False,
            "days_idle": 999.0,
        }


def audit_unmerged_branches(
    cwd: Path,
    base_branch: str = "main",
    max_idle_days: float = 14.0,
    allowlist: Set[str] | None = None,
) -> Dict[str, Any]:
    allow = set(allowlist or DEFAULT_ALLOWLIST)
    unmerged = get_unmerged_branches(cwd, base_branch)
    
    anomalies = []
    active_branches = []

    for b in unmerged:
        clean_name = b.replace("remotes/origin/", "").strip()
        if clean_name in allow or any(clean_name.startswith(p) for p in ["release/", "backup/", "staging/"]):
            continue

        info = inspect_branch_drift(b, cwd, base_branch)
        if not info.get("has_changes"):
            continue

        if info["days_idle"] > max_idle_days:
            anomalies.append({
                "branch": b,
                "days_idle": info["days_idle"],
                "last_commit": info["commit"],
                "subject": info["subject"],
                "remediation": f"分支 {b} 已脫離 {base_branch} 超過 {info['days_idle']} 天且存在代碼差異，請立即收斂合併入 {base_branch} 或刪除清理",
            })
        else:
            active_branches.append(info)

    return {
        "schema": "agentos.unmerged-branch-guard-report/v1",
        "base_branch": base_branch,
        "total_unmerged_with_diff": len(anomalies) + len(active_branches),
        "stale_orphaned_branches": len(anomalies),
        "active_feature_branches": len(active_branches),
        "verdict": "FAIL" if anomalies else "PASS",
        "anomalies": anomalies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS Unmerged Branch Guard")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    parser.add_argument("--max-days", type=float, default=14.0, help="Max idle days before warning (default: 14)")
    parser.add_argument("--fail-on-stale", action="store_true", help="Exit with non-zero code if stale unmerged branches exist")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    report = audit_unmerged_branches(repo_root, base_branch=args.base, max_idle_days=args.max_days)

    print("=== 🛡️ AgentOS Unmerged Branch Convergence Guard ===")
    print(f"基準主分支: {report['base_branch']}")
    print(f"存在代碼差異的未合併分支總數: {report['total_unmerged_with_diff']}")
    print(f"長期滯留孤島分支 (>{args.max_days} 天): {report['stale_orphaned_branches']}")
    print(f"近期活躍特性分支: {report['active_feature_branches']}")
    print(f"裁定結論: {report['verdict']}")
    
    if report["anomalies"]:
        print("\n⚠️ 發現未收斂孤島分支 (Stale Unmerged Branches):")
        for a in report["anomalies"]:
            print(f" - [{a['branch']}] 閒置 {a['days_idle']} 天 (Commit: {a['last_commit']})")
            print(f"   標題: {a['subject']}")
            print(f"   建議: {a['remediation']}")

    if args.fail_on_stale and report["verdict"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
