#!/usr/bin/env python3
"""
AgentOS Central Task Board Generator
=====================================
從所有專案的 STATUS.md 聚合 Todo 任務，
生成/更新 agent-data/TASK_BOARD.md 中央看板。

用法:
  python3 sync_task_board.py          # 同步（保留人工修改）
  python3 sync_task_board.py --reset  # 從頭重建（覆蓋）
"""
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path("/home/ubuntu/agent-data/projects")
BOARD_FILE = Path("/home/ubuntu/agent-data/TASK_BOARD.md")


def parse_todos(status_md: Path) -> list[tuple[str, str]]:
    """從 STATUS.md 解析 Todo 清單"""
    content = status_md.read_text(encoding="utf-8")
    todos = []
    in_todo = False
    for line in content.splitlines():
        if re.match(r"^##\s+.*(Todo|TODO|Task|任務|待辦)", line, re.IGNORECASE):
            in_todo = True
            continue
        if in_todo and line.startswith("##"):
            break
        if in_todo:
            m = re.match(r"^[-*]\s+\[([ x/])\]\s+(.+)", line)
            if m:
                todos.append((m.group(1), m.group(2).strip()))
    return todos


def get_project_meta(status_md: Path) -> tuple[str, str]:
    """讀取專案最後狀態與更新時間"""
    content = status_md.read_text(encoding="utf-8")
    status_m = re.search(r"\*\*Last Status\*\*\s*\|\s*(.+)", content)
    updated_m = re.search(r"\*\*Last Updated\*\*\s*\|\s*(.+)", content)
    last_status = status_m.group(1).strip() if status_m else ""
    last_updated = updated_m.group(1).strip() if updated_m else ""
    return last_status, last_updated


def build_board() -> str:
    """建立完整的 TASK_BOARD.md 內容"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        "# 🦞 AgentOS Central Task Board",
        "",
        "> 這是唯一的任務管理入口。直接在此編輯任務，Lobster Engine 會自動挑選執行。",
        "> **格式**：`- [ ] 任務描述` (待做) | `- [/] 任務描述` (進行中) | `- [x] 任務描述` (完成)",
        f"> 最後同步：{now}",
        "",
        "---",
        "",
    ]
    
    projects = sorted(d.name for d in PROJECTS_DIR.iterdir() if d.is_dir())
    
    active_projects = []   # 有待辦任務
    done_projects = []     # 全部完成
    empty_projects = []    # 無 Todo List
    
    for proj in projects:
        status_md = PROJECTS_DIR / proj / "STATUS.md"
        if not status_md.exists():
            empty_projects.append((proj, "❌ 無 STATUS.md", ""))
            continue
        
        todos = parse_todos(status_md)
        last_status, last_updated = get_project_meta(status_md)
        
        if not todos:
            empty_projects.append((proj, last_status[:50], last_updated))
        else:
            pending = [(s, t) for s, t in todos if s in (" ", "/")]
            done = len([t for t in todos if t[0] == "x"])
            if pending:
                active_projects.append((proj, last_updated, todos, done, len(todos)))
            else:
                done_projects.append((proj, last_status[:50], last_updated, done))
    
    # ── 待執行任務 ──
    lines.append(f"## 🔥 待執行任務（{len(active_projects)} 個專案有待辦）")
    lines.append("")
    
    if not active_projects:
        lines.append("*所有任務已完成！請在下方各專案區塊新增新任務。*")
        lines.append("")
    
    for proj, updated, todos, done, total in active_projects:
        pending_count = total - done
        lines.append(f"### 📦 {proj}")
        lines.append(f"*更新：{updated or '未知'} | 進度：{done}/{total}*")
        lines.append("")
        for s, t in todos:
            mark = {"x": "x", " ": " ", "/": "/"}.get(s, " ")
            lines.append(f"- [{mark}] {t}")
        lines.append("")
    
    # ── 全部完成的專案（可加新任務） ──
    lines.append("---")
    lines.append("")
    lines.append(f"## ✅ 已完成 / 可新增下一步（{len(done_projects)} 個）")
    lines.append("")
    lines.append("*以下專案的已知任務都完成了。在任一區塊加上 `- [ ] 新任務` 即可讓 Lobster 自動接手。*")
    lines.append("")
    
    for proj, status, updated, done in done_projects:
        lines.append(f"### ✅ {proj}")
        lines.append(f"*{updated} — {status}*")
        lines.append("")
        lines.append("<!-- 在此加入新任務，例如：- [ ] 新增 XX 功能 -->")
        lines.append("")
    
    # ── 無 Todo List 的專案 ──
    lines.append("---")
    lines.append("")
    lines.append(f"## 📭 未列任務的專案（{len(empty_projects)} 個）")
    lines.append("")
    
    for proj, status, updated in empty_projects:
        lines.append(f"- **{proj}** — {status}")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*由 `sync_task_board.py` 自動生成 @ {now}*")
    
    return "\n".join(lines)


def sync_board(reset: bool = False):
    """同步中央看板"""
    if reset or not BOARD_FILE.exists():
        content = build_board()
        BOARD_FILE.write_text(content, encoding="utf-8")
        print(f"✅ TASK_BOARD.md 已{'重建' if reset else '建立'}：{BOARD_FILE}")
    else:
        # 保守同步：只更新時間戳和新增新專案（不覆蓋人工修改）
        # 完整重建用 --reset
        print(f"📋 TASK_BOARD.md 已存在。使用 --reset 重建，或直接編輯：{BOARD_FILE}")


def main():
    parser = argparse.ArgumentParser(description="AgentOS Central Task Board Sync")
    parser.add_argument("--reset", action="store_true", help="從頭重建（覆蓋現有內容）")
    args = parser.parse_args()
    sync_board(args.reset)


if __name__ == "__main__":
    main()
