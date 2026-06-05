#!/usr/bin/env python3
"""
🧙 AgentOS Architect Agent
===========================
讀取 WISHES.md 中的許願，呼叫 Claude 展開成：
  - 技術規格（背景 + 目標）
  - 驗收條件（Inspector 用）
  - 具體 Todo 任務清單（Lobster 用）

然後寫入 TASK_BOARD.md 對應專案，並標記 WISHES.md。

用法:
  python3 architect.py              # 處理下一個許願
  python3 architect.py --dry-run    # 只顯示，不寫入
  python3 architect.py --wish "..."  # 直接處理指定許願
"""
import os
import re
import sys
import json
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (🧙 Architect) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/ubuntu/agent-data/logs/architect.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("Architect")

HOME = Path("/home/ubuntu")
AGENT_DATA = HOME / "agent-data"
WISHES_FILE = AGENT_DATA / "WISHES.md"
TASK_BOARD = AGENT_DATA / "TASK_BOARD.md"
PROJECTS_DIR = AGENT_DATA / "projects"

def _find_claude_bin() -> Path:
    extensions_dir = HOME / ".antigravity-ide-server/extensions"
    if extensions_dir.exists():
        matches = list(extensions_dir.glob("anthropic.claude-code-*"))
        if matches:
            matches.sort()
            latest = matches[-1]
            binary_path = latest / "resources/native-binary/claude"
            if binary_path.exists():
                return binary_path
    return HOME / ".antigravity-ide-server/extensions/anthropic.claude-code-2.1.156-linux-arm64/resources/native-binary/claude"

CLAUDE_BIN = _find_claude_bin()

MAX_TASKS_PER_WISH = 7  # 超過這個數量要求再拆分


def load_env():
    env_path = HOME / "agentmanager/.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()


# ── WISHES.md 管理 ─────────────────────────────────────────────────────────

def ensure_wishes_file():
    """確保 WISHES.md 存在，若不存在則建立範本"""
    if not WISHES_FILE.exists():
        WISHES_FILE.write_text(
            "# 🌟 AgentOS Wishes Board\n\n"
            "> 在這裡寫下你的需求（一句話）。Architect 會自動展開成任務。\n"
            "> 格式：`- [ ] [專案名稱] 需求描述`\n\n"
            "## 待處理\n\n"
            "<!-- 在這裡加入新許願，例如：-->\n"
            "<!-- - [ ] [youtube-ai-manager] 新增批量下載最受歡迎影片功能 -->\n\n"
            "## 處理中\n\n"
            "## 已完成\n\n",
            encoding="utf-8",
        )
        logger.info(f"✨ 建立 WISHES.md: {WISHES_FILE}")


def parse_wishes() -> list[dict]:
    """解析 WISHES.md，返回待處理許願清單"""
    if not WISHES_FILE.exists():
        return []

    content = WISHES_FILE.read_text(encoding="utf-8")
    wishes = []
    in_pending = False

    for line in content.splitlines():
        if re.match(r"^##\s+待處理", line):
            in_pending = True
            continue
        if in_pending and line.startswith("##"):
            break
        if in_pending:
            # 格式: - [ ] [project-name] 需求描述
            m = re.match(r"^[-*]\s+\[([ x/])\]\s+\[([^\]]+)\]\s+(.+)", line)
            if m and m.group(1) == " ":
                wishes.append({
                    "status": "todo",
                    "project": m.group(2).strip(),
                    "text": m.group(3).strip(),
                    "raw_line": line,
                })

    return wishes


def update_wish_status(wish: dict, new_status: str):
    """更新 WISHES.md 中許願的狀態"""
    content = WISHES_FILE.read_text(encoding="utf-8")
    old_line = wish["raw_line"]
    status_map = {"in_progress": "/", "done": "x", "todo": " "}
    new_mark = status_map.get(new_status, " ")
    new_line = re.sub(r"\[([ x/])\]", f"[{new_mark}]", old_line, count=1)
    content = content.replace(old_line, new_line, 1)

    # 如果完成，移到「已完成」區塊
    if new_status == "done" and "## 已完成" in content:
        content = content.replace(new_line + "\n", "", 1)
        content = content.replace(
            "## 已完成\n\n",
            f"## 已完成\n\n{new_line}\n",
            1,
        )

    WISHES_FILE.write_text(content, encoding="utf-8")


# ── Claude 呼叫 ────────────────────────────────────────────────────────────

def expand_wish_with_claude(project: str, wish_text: str) -> Optional[str]:
    """呼叫 Claude 將許願展開成規格 + 任務清單（JSON 格式）"""
    prompt = f"""你是 AgentOS 架構師（Architect Agent）。
你的工作是把一個簡短的需求展開成可執行的開發計劃。

## 許願內容
專案：{project}
需求：{wish_text}

## 專案目錄
/home/ubuntu/{project}/

## 任務
請將以上需求展開為以下 JSON 格式（必須是合法 JSON，不要加 markdown 代碼塊）：

{{
  "spec": "一段技術規格說明（100-200 字）",
  "acceptance_criteria": ["驗收條件 1", "驗收條件 2"],
  "tasks": [
    "具體可執行的任務 1（動詞開頭，20-50 字）",
    "具體可執行的任務 2",
    ...
  ]
}}

規則：
- tasks 最多 {MAX_TASKS_PER_WISH} 個，每個任務必須是獨立可執行的
- 任務描述要清楚到 Lobster AI 可以直接執行，不需要問問題
- 如果需求太大，tasks 只列第一個可交付的 milestone
- 使用繁體中文
"""
    cmd = [
        str(CLAUDE_BIN),
        "--print",
        "--output-format", "text",
        "--max-tokens", "4000",
        "--no-session-persistence",
        prompt,
    ]

    proj_dir = HOME / project
    cwd = str(proj_dir) if proj_dir.exists() else str(HOME)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ},
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Claude 失敗 (exit {result.returncode}): {result.stderr[:200]}")
            return None
    except Exception as e:
        logger.error(f"呼叫 Claude 異常: {e}")
        return None


def parse_claude_response(raw: str) -> Optional[dict]:
    """從 Claude 輸出中提取 JSON"""
    # 嘗試直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 嘗試提取 JSON 區塊
    json_match = re.search(r"\{[\s\S]+\}", raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    logger.error(f"無法解析 Claude 輸出為 JSON: {raw[:200]}")
    return None


# ── TASK_BOARD.md 更新 ────────────────────────────────────────────────────

def append_tasks_to_board(project: str, wish_text: str, plan: dict):
    """將展開的任務追加到 TASK_BOARD.md 的對應專案區塊"""
    if not TASK_BOARD.exists():
        logger.error("TASK_BOARD.md 不存在！請先執行 sync_task_board.py")
        return False

    content = TASK_BOARD.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 構建新任務區塊
    tasks_block = f"\n<!-- 由 Architect 從許願展開 @ {now} -->\n"
    tasks_block += f"<!-- 許願：{wish_text} -->\n"
    if plan.get("spec"):
        tasks_block += f"<!-- 規格：{plan['spec'][:100]}... -->\n"
    for task in plan.get("tasks", []):
        tasks_block += f"- [ ] {task}\n"

    # 找到對應專案的區塊並插入
    proj_pattern = re.compile(
        r"(### [^\n]*" + re.escape(project) + r"[^\n]*\n(?:.*\n)*?)((?=###)|$)",
        re.MULTILINE,
    )
    match = proj_pattern.search(content)

    if match:
        # 在現有專案區塊末尾插入
        insert_pos = match.end(1)
        content = content[:insert_pos] + tasks_block + content[insert_pos:]
    else:
        # 專案不存在，在「待執行任務」區塊追加
        new_section = f"\n### 📦 {project}\n*由 Architect 建立 @ {now}*\n{tasks_block}\n"
        if "## 🔥 待執行任務" in content:
            content = content.replace(
                "## 🔥 待執行任務",
                f"## 🔥 待執行任務",
                1,
            )
            # 找到第一個 ### 之前插入
            first_proj = re.search(r"\n### ", content)
            if first_proj:
                content = content[: first_proj.start()] + new_section + content[first_proj.start():]
            else:
                content += new_section
        else:
            content += new_section

    TASK_BOARD.write_text(content, encoding="utf-8")
    logger.info(f"✅ 已將 {len(plan.get('tasks', []))} 個任務寫入 TASK_BOARD.md [{project}]")
    return True


# ── 主流程 ────────────────────────────────────────────────────────────────

def process_wish(wish: dict, dry_run: bool = False) -> bool:
    """處理一個許願：展開 → 寫入 TASK_BOARD"""
    project = wish["project"]
    text = wish["text"]

    logger.info(f"🧙 展開許願: [{project}] {text}")

    if dry_run:
        logger.info("[DRY RUN] 跳過 Claude 呼叫")
        logger.info(f"[DRY RUN] 會在 TASK_BOARD.md [{project}] 新增任務")
        return True

    # 標記為處理中
    update_wish_status(wish, "in_progress")

    # 呼叫 Claude 展開
    raw_response = expand_wish_with_claude(project, text)
    if not raw_response:
        logger.error("Claude 無回應，回滾許願狀態")
        update_wish_status(wish, "todo")
        return False

    # 解析回應
    plan = parse_claude_response(raw_response)
    if not plan or not plan.get("tasks"):
        logger.error(f"無法解析規格，原始輸出: {raw_response[:300]}")
        update_wish_status(wish, "todo")
        return False

    tasks = plan["tasks"]
    logger.info(f"📋 展開成 {len(tasks)} 個任務:")
    for i, t in enumerate(tasks, 1):
        logger.info(f"  {i}. {t}")

    # 寫入 TASK_BOARD
    if not append_tasks_to_board(project, text, plan):
        update_wish_status(wish, "todo")
        return False

    # 標記許願完成
    update_wish_status(wish, "done")
    logger.info(f"🌟 許願已展開完畢: [{project}] {text}")
    return True


def main():
    parser = argparse.ArgumentParser(description="🧙 Architect Agent - 許願展開器")
    parser.add_argument("--dry-run", action="store_true", help="只顯示，不實際寫入")
    parser.add_argument("--wish", type=str, help="直接指定許願文字（格式：[專案] 需求）")
    args = parser.parse_args()

    ensure_wishes_file()

    if args.wish:
        # 解析 --wish 格式
        m = re.match(r"\[([^\]]+)\]\s+(.+)", args.wish)
        if not m:
            logger.error("格式錯誤。請使用：--wish '[專案名] 需求描述'")
            return 1
        wish = {
            "status": "todo",
            "project": m.group(1).strip(),
            "text": m.group(2).strip(),
            "raw_line": f"- [ ] [{m.group(1)}] {m.group(2)}",
        }
        process_wish(wish, args.dry_run)
    else:
        wishes = parse_wishes()
        if not wishes:
            logger.info("📭 WISHES.md 中沒有待處理的許願")
            logger.info(f"請在此檔案中新增許願: {WISHES_FILE}")
            return 0

        logger.info(f"🌟 找到 {len(wishes)} 個待處理許願，處理第一個...")
        process_wish(wishes[0], args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
