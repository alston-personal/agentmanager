#!/usr/bin/env python3
"""
Themis Project Inventory & Temporal Delta Diff Engine (/project-diff)
執掌神祇: governance.themis_command_steward (忒彌斯 · 專案天平與差分審計)

提供單一專案島嶼的深度時序差分比對:
1. 產出物清單變遷 (Artifacts Delta)
2. 待辦任務演進 (Open/Closed TODOs & ACs)
3. 程式碼版本歷程 (Git branch, commit, clean status)
4. 邏輯與資料分離架構檢驗 (Symlink Bridge & Logic/Data separation)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AGENTMANAGER_DEFAULT = Path("/home/ubuntu/agentmanager")
AGENT_DATA_DEFAULT = Path("/home/ubuntu/agent-data")
HOME_DIR = Path("/home/ubuntu")


def validate_authoritative_data_root(data_root: Path) -> None:
    expected_real = Path("/home/ubuntu/agent-data").resolve()
    actual_real = data_root.resolve()
    if actual_real != expected_real:
        raise RuntimeError(
            f"REFUSING_NON_AUTHORITATIVE_DATA_ROOT: Themis requires authoritative data_root "
            f"'{expected_real}', got '{actual_real}'."
        )


def find_project_dirs(project_name: str, data_root: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """尋找專案之資料目錄 (agent-data/projects/...) 與邏輯代碼目錄 (/home/ubuntu/...)。"""
    data_dir = data_root / "projects" / project_name
    if not data_dir.exists():
        data_dir = None

    # 檢查邏輯目錄: /home/ubuntu/<project_name>
    logic_dir = HOME_DIR / project_name
    if not logic_dir.exists() or not logic_dir.is_dir():
        # 若是 agentmanager 本身
        if project_name == "agentmanager":
            logic_dir = AGENTMANAGER_DEFAULT
        else:
            logic_dir = None

    return data_dir, logic_dir


def check_symlink_health(project_name: str, logic_dir: Optional[Path], data_dir: Optional[Path]) -> Dict[str, Any]:
    """檢測專案是否遵守 Logic/Data 分離規範與軟連結橋接。"""
    health = {
        "status_symlink_valid": False,
        "memory_symlink_valid": False,
        "violations": [],
    }
    if not logic_dir or not logic_dir.exists():
        health["violations"].append("No local logic workspace found in /home/ubuntu")
        return health

    # 1. 檢查 STATUS.md
    logic_status = logic_dir / "STATUS.md"
    if logic_status.is_symlink():
        target = logic_status.resolve()
        if data_dir and target == (data_dir / "STATUS.md").resolve():
            health["status_symlink_valid"] = True
        else:
            health["violations"].append(f"STATUS.md symlink points to unexpected target: {target}")
    elif logic_status.exists():
        health["violations"].append("STATUS.md is a physical file in logic repo (violates Logic/Data separation)")
    else:
        health["violations"].append("STATUS.md missing in logic workspace")

    # 2. 檢查 memory/ (若存在)
    logic_memory = logic_dir / "memory"
    if logic_memory.is_symlink():
        target = logic_memory.resolve()
        if data_dir and target == (data_dir / "memory").resolve():
            health["memory_symlink_valid"] = True
        else:
            health["violations"].append(f"memory/ symlink points to unexpected target: {target}")
    elif logic_memory.exists() and logic_memory.is_dir():
        health["violations"].append("memory/ is a physical directory in logic repo")

    return health


def parse_project_status(data_dir: Path) -> Dict[str, Any]:
    """解析專案 STATUS.md 內容與 TODO 清單。"""
    status_file = data_dir / "STATUS.md"
    if not status_file.exists():
        return {
            "has_status": False,
            "open_todos": [],
            "closed_todos": [],
            "todos_with_ac": [],
            "open_count": 0,
            "closed_count": 0,
            "ac_count": 0,
            "activity_log": [],
        }

    open_todos = []
    closed_todos = []
    todos_with_ac = []
    activity_log = []
    in_log = False

    try:
        content = status_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            clean = line.strip()
            if "<!-- LOG_START -->" in clean:
                in_log = True
                continue
            if "<!-- LOG_END -->" in clean:
                in_log = False
                continue
            if in_log and clean.startswith("- `"):
                activity_log.append(clean[2:])

            if clean.startswith("- [ ]"):
                task_text = clean[5:].strip()
                open_todos.append(task_text)
                if any(m in task_text for m in ("[AC:", "[驗收:", "驗收標準", "acceptance", "驗收: `")):
                    todos_with_ac.append(task_text)
            elif clean.startswith("- [x]"):
                closed_todos.append(clean[5:].strip())
    except Exception as exc:
        activity_log.append(f"Failed to read STATUS.md: {exc}")

    return {
        "has_status": True,
        "open_todos": open_todos,
        "closed_todos": closed_todos,
        "todos_with_ac": todos_with_ac,
        "open_count": len(open_todos),
        "closed_count": len(closed_todos),
        "ac_count": len(todos_with_ac),
        "activity_log": activity_log[:5],
    }


def get_git_status(repo_dir: Path) -> Dict[str, Any]:
    """讀取專案之 Git 狀態。"""
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return {"is_git": False}

    info = {"is_git": True, "branch": "unknown", "commit_sha": "unknown", "is_clean": True, "recent_commits": []}
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        info["branch"] = out

        sha = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        info["commit_sha"] = sha

        status_out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        info["is_clean"] = len(status_out) == 0

        logs = subprocess.check_output(
            ["git", "-C", str(repo_dir), "log", "-n", "3", "--oneline"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        info["recent_commits"] = logs.splitlines() if logs else []
    except Exception:
        pass

    return info


def get_recent_artifacts(logic_dir: Optional[Path], data_dir: Optional[Path], since_seconds: int = 86400 * 2) -> List[Dict[str, Any]]:
    """掃描專案最近異動的實體產出物。"""
    artifacts = []
    cutoff = time.time() - since_seconds

    paths_to_scan = []
    if logic_dir and logic_dir.exists():
        paths_to_scan.append((logic_dir, "logic"))
    if data_dir and data_dir.exists():
        paths_to_scan.append((data_dir, "data"))

    ignored_dirs = {"node_modules", ".git", "__pycache__", "venv", ".next", ".astro", "dist", "build"}

    for base_path, scope in paths_to_scan:
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
            for f in files:
                if f.startswith("."):
                    continue
                fp = Path(root) / f
                try:
                    stat = fp.stat()
                    if stat.st_mtime >= cutoff:
                        artifacts.append({
                            "scope": scope,
                            "path": str(fp.relative_to(base_path)),
                            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "size_bytes": stat.st_size,
                        })
                except Exception:
                    pass

    return sorted(artifacts, key=lambda x: x["mtime"], reverse=True)[:15]


def capture_project_snapshot(project_name: str, data_root: Path = AGENT_DATA_DEFAULT) -> Dict[str, Any]:
    """獲取單一專案的當前天平快照。"""
    data_dir, logic_dir = find_project_dirs(project_name, data_root)
    if not data_dir and not logic_dir:
        raise ValueError(f"PROJECT_NOT_FOUND: Project '{project_name}' does not exist in data or logic root.")

    parsed_status = parse_project_status(data_dir) if data_dir else {"has_status": False}
    symlink_health = check_symlink_health(project_name, logic_dir, data_dir)
    git_info = get_git_status(logic_dir) if logic_dir else {"is_git": False}
    recent_files = get_recent_artifacts(logic_dir, data_dir)

    return {
        "project": project_name,
        "timestamp": datetime.now().astimezone().isoformat(),
        "has_logic_repo": logic_dir is not None,
        "has_data_repo": data_dir is not None,
        "status": parsed_status,
        "symlink_health": symlink_health,
        "git": git_info,
        "recent_artifacts": recent_files,
    }


def compute_project_delta(project_name: str, current: Dict[str, Any], data_root: Path) -> Dict[str, Any]:
    """比對當前專案與全域最新/指定快照之時序差異。"""
    snapshots_dir = data_root / "snapshots" / "inventory"
    delta = {
        "has_baseline": False,
        "message": "No baseline snapshot found for project diff comparison",
    }
    if not snapshots_dir.exists():
        return delta

    snap_files = sorted(snapshots_dir.glob("snapshot-*.json"))
    if not snap_files:
        return delta

    # 讀取最新基準快照
    baseline_file = snap_files[-1]
    try:
        baseline_data = json.loads(baseline_file.read_text(encoding="utf-8"))
    except Exception as exc:
        delta["message"] = f"Failed to load baseline {baseline_file.name}: {exc}"
        return delta

    prev_proj = baseline_data.get("projects", {}).get(project_name)
    if not prev_proj:
        delta["message"] = f"Project '{project_name}' was not present in baseline {baseline_file.name}"
        return delta

    c_stat = current.get("status", {})
    delta["has_baseline"] = True
    delta["baseline_file"] = baseline_file.name
    delta["baseline_timestamp"] = baseline_data.get("timestamp", "unknown")
    delta["current_timestamp"] = current.get("timestamp", "unknown")

    # 任務增減
    old_open = prev_proj.get("open_count", 0)
    new_open = c_stat.get("open_count", 0)
    old_closed = prev_proj.get("closed_count", 0)
    new_closed = c_stat.get("closed_count", 0)

    delta["open_delta"] = new_open - old_open
    delta["closed_delta"] = new_closed - old_closed

    # 比對哪些任務被完成
    old_open_todos = set(prev_proj.get("open_todos", []))
    new_open_todos = set(c_stat.get("open_todos", []))
    delta["resolved_todos"] = list(old_open_todos - new_open_todos)
    delta["new_todos"] = list(new_open_todos - old_open_todos)

    return delta


def format_project_markdown_report(current: Dict[str, Any], delta: Dict[str, Any]) -> str:
    """生成針對單一專案島嶼的詳細天平審計報告。"""
    proj = current["project"]
    c_stat = current.get("status", {})
    git = current.get("git", {})
    health = current.get("symlink_health", {})

    lines = [
        f"# ⚖️ 忒彌斯專案時序審計報告: `{proj}`",
        f"**審計時間**：`{current.get('timestamp')}`  ",
        f"**執掌神祇**：`governance.themis_command_steward` (天平與差分審計)  ",
        "",
        "---",
        "",
        "## 🏗️ 1. 架構合規與身心健康 (Architecture & Symlink Bridge)",
        f"- **代碼倉庫 (Logic)**：`{'已建立 (/home/ubuntu/' + proj + ')' if current.get('has_logic_repo') else '無獨立代碼目錄'}`",
        f"- **資料中心 (Data)**：`{'已存在 (/home/ubuntu/agent-data/projects/' + proj + ')' if current.get('has_data_repo') else '未建檔'}`",
    ]

    if health.get("violations"):
        lines.append("- ⚠️ **合規警示 (Violations)**：")
        for v in health["violations"]:
            lines.append(f"  - `{v}`")
    else:
        lines.append("- ✅ **架構驗證**：嚴格遵守 Logic/Data 物理分離，STATUS.md 軟連結指向正確。")

    if git.get("is_git"):
        lines.append(f"- **代碼主幹**：`{git.get('branch')}` @ `{git.get('commit_sha')[:8]}` (乾淨狀態: `{git.get('is_clean')}`)")
        if git.get("recent_commits"):
            lines.append("  - **近期提交**：")
            for c in git["recent_commits"]:
                lines.append(f"    - `{c}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. 任務閉環動態
    lines.append("## 📋 2. 待辦任務與驗收狀態 (Tasks & Milestones)")
    lines.append(f"- **進行中待辦 (Open)**：`{c_stat.get('open_count', 0)}` 項")
    lines.append(f"- **已完成任務 (Closed)**：`{c_stat.get('closed_count', 0)}` 項")
    lines.append(f"- **具備驗收標記 (With AC)**：`{c_stat.get('ac_count', 0)}` 項")

    if delta.get("has_baseline"):
        lines.append("")
        lines.append(f"> 基準點快照：`{delta.get('baseline_file')}` (`{delta.get('baseline_timestamp')}`)")
        lines.append(f"- **待辦消長**：Open `{delta.get('open_delta', 0):+d}`，Closed `{delta.get('closed_delta', 0):+d}`")
        if delta.get("resolved_todos"):
            lines.append("### 🎉 新近閉環任務 (Resolved since baseline):")
            for t in delta["resolved_todos"]:
                lines.append(f"  - [x] {t}")
        if delta.get("new_todos"):
            lines.append("### 📝 新增待辦任務 (Added since baseline):")
            for t in delta["new_todos"]:
                lines.append(f"  - [ ] {t}")
    lines.append("")

    # 當前待辦列舉
    if c_stat.get("open_todos"):
        lines.append("### ⏳ 當前排隊待辦 (Open Tasks):")
        for t in c_stat["open_todos"]:
            lines.append(f"  - [ ] {t}")
        lines.append("")

    # 3. 實體產出物異動
    artifacts = current.get("recent_artifacts", [])
    lines.append("---")
    lines.append("")
    lines.append("## 📦 3. 新近實體產出物歷程 (Recent Artifacts Modified)")
    if artifacts:
        lines.append("| 領域 | 相對路徑 | 異動時間 | 大小 |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for a in artifacts:
            lines.append(f"| `{a['scope']}` | `{a['path']}` | `{a['mtime'][:19]}` | `{a['size_bytes']} B` |")
    else:
        lines.append("> 48 小時內無偵測到實體文件異動。")

    # 4. 活動日誌
    if c_stat.get("activity_log"):
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 📜 4. 最新活動日誌 (Activity Log)")
        for log in c_stat["activity_log"]:
            lines.append(f"- {log}")

    return "\n".join(lines)


def run_project_diff(project_name: str, data_root: Path = AGENT_DATA_DEFAULT, json_output: bool = False) -> Tuple[Dict[str, Any], str]:
    validate_authoritative_data_root(data_root)
    current = capture_project_snapshot(project_name, data_root)
    delta = compute_project_delta(project_name, current, data_root)
    report = format_project_markdown_report(current, delta)

    result = {
        "schema": "agentos.themis-project-diff/v1",
        "steward": "governance.themis_command_steward",
        "project": project_name,
        "current": current,
        "delta": delta,
    }
    return result, report


def main():
    parser = argparse.ArgumentParser(description="Themis Project-Level Temporal Delta Diff Engine (/project-diff)")
    parser.add_argument("project", help="Name of the project island to inspect (e.g. zeus-writer, social-galaxy)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--allow-non-authoritative", action="store_true", help="Allow running on non-authoritative root")
    args = parser.parse_args()

    data_root = AGENT_DATA_DEFAULT
    if not args.allow_non_authoritative:
        validate_authoritative_data_root(data_root)

    try:
        result, report = run_project_diff(args.project, data_root=data_root, json_output=args.json)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(report)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
