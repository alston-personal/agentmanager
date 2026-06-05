#!/usr/bin/env python3
"""
🚀 AgentOS Pipeline Controller
================================
協調 Architect + Lobster + Inspector + Reporter，
實現從許願到完成的全自動 5 階段開發流水線。

流程:
  WISHES.md [ ] 許願
    → 🧙 Architect 展開 → TASK_BOARD.md tasks
    → 🦞 Lobster 執行 task
    → 🔍 Inspector 驗證（最多重試 3 次）
      → PASS: TASK_BOARD.md [x] → 繼續下一個
      → BLOCKED: TASK_BOARD.md [!] → Telegram 告警 → 停止
    → 所有 tasks [x] → 📢 Reporter → Telegram 完成通知

用法:
  python3 pipeline.py              # 處理一個許願並執行到完成
  python3 pipeline.py --loop       # 持續監控 WISHES.md 並執行
  python3 pipeline.py --dry-run    # 模擬執行，不實際呼叫 Claude
  python3 pipeline.py --skip-arch  # 跳過 Architect（TASK_BOARD 已有任務）
"""
import os
import re
import sys
import json
import time
import signal
import logging
import argparse
import requests
from datetime import datetime
from pathlib import Path

# 引入同目錄的模組
sys.path.insert(0, str(Path(__file__).parent))
import inspector as Inspector
import lobster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (🚀 Pipeline) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/ubuntu/agent-data/logs/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("Pipeline")

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

MAX_RETRIES = 3
TASK_TIMEOUT = 300
MAX_TOKENS = 8000
LOOP_INTERVAL = 120  # seconds between wish checks


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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")


# ── Telegram 通知 ─────────────────────────────────────────────────────────

def send_telegram(message: str):
    """發送 Telegram 通知"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ Telegram 未配置，跳過通知")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)
        logger.info("📢 Telegram 通知已發送")
    except Exception as e:
        logger.warning(f"Telegram 發送失敗: {e}")


# ── TASK_BOARD 狀態管理 ────────────────────────────────────────────────────

def read_board_tasks(project: str) -> list[dict]:
    """讀取 TASK_BOARD.md 中特定專案的任務"""
    if not TASK_BOARD.exists():
        return []

    content = TASK_BOARD.read_text(encoding="utf-8")
    tasks = []
    in_project = False

    for line in content.splitlines():
        proj_m = re.match(r"^###\s+[\S]+\s+([\w\-]+)\s*$", line)
        if proj_m:
            in_project = (proj_m.group(1) == project)
            continue
        if in_project and line.startswith("###"):
            break
        if in_project:
            m = re.match(r"^[-*]\s+\[([ x/!])\]\s+(.+)", line)
            if m:
                status_map = {" ": "todo", "x": "done", "/": "in_progress", "!": "blocked"}
                tasks.append({
                    "status": status_map.get(m.group(1), "unknown"),
                    "text": m.group(2).strip(),
                    "raw_line": line,
                })

    return tasks


def update_board_task(task_text: str, new_status: str):
    """更新 TASK_BOARD.md 中的任務狀態"""
    if not TASK_BOARD.exists():
        return
    status_map = {"todo": " ", "in_progress": "/", "done": "x", "blocked": "!"}
    mark = status_map.get(new_status, " ")
    content = TASK_BOARD.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(^[-*]\s+\[)[ x/!](\]\s+" + re.escape(task_text) + r")",
        re.MULTILINE,
    )
    new_content = pattern.sub(rf"\g<1>{mark}\g<2>", content, count=1)
    if new_content != content:
        TASK_BOARD.write_text(new_content, encoding="utf-8")


# ── Lobster 執行（單一任務）─────────────────────────────────────────────────

def run_task(project: str, task_text: str, dry_run: bool = False) -> tuple[bool, str]:
     """呼叫 Claude --print 執行一個任務（delegate 給 lobster）"""
     return lobster.run_claude_task(project, {"text": task_text}, dry_run)



def run_pipeline_for_project(project: str, wish_text: str = "", dry_run: bool = False) -> bool:
    """
    對指定專案執行完整流水線：
    讀取 TASK_BOARD 待辦任務 → 逐一執行 + 驗證 → 完成通知
    """
    logger.info(f"━━━ Pipeline 啟動 [{project}] ━━━")
    if wish_text:
        logger.info(f"許願來源: {wish_text}")

    tasks = read_board_tasks(project)
    pending = [t for t in tasks if t["status"] in ("todo", "in_progress")]

    if not pending:
        logger.info(f"📭 [{project}] 沒有待處理任務")
        return True

    logger.info(f"📋 [{project}] 待執行任務: {len(pending)} 個")

    completed = []
    blocked = []

    for task in pending:
        task_text = task["text"]
        logger.info(f"🚀 執行任務: {task_text[:60]}")

        # 標記為進行中
        update_board_task(task_text, "in_progress")

        # 執行任務並用 Inspector 驗證
        success, output = lobster.run_with_inspector(HOME / project, task_text, dry_run)

        if success:
            final_result = "PASS"
            final_reason = output.replace("PASS: ", "", 1)
        else:
            if "BLOCKED:" in output:
                final_result = "BLOCKED"
                final_reason = output.replace("BLOCKED: ", "", 1)
            else:
                final_result = "FAIL"
                final_reason = output.replace("FAIL: ", "", 1)

        # 更新 TASK_BOARD 狀態
        if final_result == "PASS":
            update_board_task(task_text, "done")
            completed.append(task_text)
            logger.info(f"✅ 任務完成: {task_text[:50]}")

            # 同步 Activity Log
            status_md = PROJECTS_DIR / project / "STATUS.md"
            if status_md.exists():
                content = status_md.read_text(encoding="utf-8")
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                entry = f"- `{now}` 🚀 **[Pipeline]** 完成任務：{task_text[:60]}"
                if "<!-- LOG_START -->" in content:
                    content = content.replace("<!-- LOG_START -->", f"<!-- LOG_START -->\n{entry}", 1)
                    status_md.write_text(content, encoding="utf-8")
        else:
            update_board_task(task_text, "blocked")
            blocked.append((task_text, final_reason))
            logger.warning(f"🚫 任務阻斷: {task_text[:50]}")

            # 立即發 Telegram 告警
            send_telegram(
                f"🚫 *Pipeline 阻斷告警*\n\n"
                f"專案: `{project}`\n"
                f"任務: {task_text[:80]}\n"
                f"原因: {final_reason[:200]}\n\n"
                f"請人工介入後在 TASK_BOARD.md 將 `[!]` 改為 `[ ]` 以恢復執行。"
            )
            break  # 遇到阻斷就停止這個專案的後續任務

    # 完成報告
    total = len(pending)
    done_count = len(completed)

    if blocked:
        logger.warning(f"⚠️ [{project}] 完成 {done_count}/{total}，{len(blocked)} 個阻斷")
        return False
    else:
        logger.info(f"🎉 [{project}] 全部 {done_count}/{total} 任務完成！")
        if wish_text:
            send_telegram(
                f"🎉 *Pipeline 完成通知*\n\n"
                f"許願: {wish_text}\n"
                f"專案: `{project}`\n"
                f"完成任務: {done_count}/{total}\n\n"
                + "\n".join(f"✅ {t[:60]}" for t in completed)
            )
        return True


def run_with_architect(dry_run: bool = False) -> bool:
       """先執行 Architect 展開許願，再執行流水線"""
       import architect
       return architect.main(dry_run=dry_run) == 0
       return architect.main(dry_run=dry_run) == 0


def main():
    parser = argparse.ArgumentParser(description="🚀 AgentOS Pipeline Controller")
    parser.add_argument("--loop", action="store_true", help="持續監控模式")
    parser.add_argument("--project", "-p", type=str, help="只處理指定專案")
    parser.add_argument("--dry-run", action="store_true", help="模擬執行")
    parser.add_argument("--skip-arch", action="store_true", help="跳過 Architect（直接從 TASK_BOARD 執行）")
    args = parser.parse_args()

    running = [True]
    def handle_signal(sig, frame):
        logger.info("🛑 收到停止信號...")
        running[0] = False
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("🚀 Pipeline Controller 啟動！")
    send_telegram("🚀 *AgentOS Pipeline* 已啟動，開始監控許願板...")

    iteration = 0
    while running[0]:
        iteration += 1
        logger.info(f"━━━ 迭代 #{iteration} ━━━")

        if not args.skip_arch:
            logger.info("🧙 執行 Architect（許願展開）...")
            run_with_architect(args.dry_run)

        # 讀取 TASK_BOARD 中有待辦任務的專案
        if args.project:
            run_pipeline_for_project(args.project, dry_run=args.dry_run)
        else:
            # 掃描所有專案
            if TASK_BOARD.exists():
                content = TASK_BOARD.read_text(encoding="utf-8")
                proj_pattern = re.finditer(r"^###\s+[\S]+\s+([\w\-]+)\s*$", content, re.MULTILINE)
                for match in proj_pattern:
                    if not running[0]:
                        break
                    proj = match.group(1)
                    tasks = read_board_tasks(proj)
                    if any(t["status"] in ("todo", "in_progress") for t in tasks):
                        run_pipeline_for_project(proj, dry_run=args.dry_run)

        if not args.loop:
            break

        logger.info(f"😴 等待 {LOOP_INTERVAL}s 後重新掃描...")
        for _ in range(LOOP_INTERVAL):
            if not running[0]:
                break
            time.sleep(1)

    logger.info("🚀 Pipeline Controller 停止。")


if __name__ == "__main__":
    main()
