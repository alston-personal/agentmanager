#!/usr/bin/env python3
"""
🦞 AgentOS Autonomous Task Loop (Lobster Engine)
================================================
讀取所有專案的 STATUS.md TODO 清單，自動挑選未完成任務，
使用 Claude Code CLI (--print 模式) 非互動執行，
並在完成後更新 STATUS.md，形成永動自律執行迴圈。

執行方式:
  python3 lobster.py               # 一次執行一個任務
  python3 lobster.py --loop        # 持續迴圈 (永動機)
  python3 lobster.py --project youtube-ai-manager  # 指定專案
  python3 lobster.py --dry-run     # 只顯示會做什麼，不實際執行
"""
import os
import re
import sys
import json
import time
import signal
import logging
import argparse
import subprocess
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 引入 Inspector 驗證模組
sys.path.insert(0, str(Path(__file__).parent))
try:
    import inspector as Inspector
except ImportError:
    Inspector = None
    logger = logging.getLogger("Lobster")
    logger.warning("⚠️ Inspector 模組未載入，無驗證功能")

# Telegram 通知配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

# ── Telegram 通知 ─────────────────────────────────────────────────────────

def send_telegram_alert(message: str):
    """發送 Telegram 警報通知"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass


def run_with_inspector(proj_dir: Path, task_text: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    執行任務並用 Inspector 驗證。最多重試 3 次。
    返回 (success, result_string)
    result_string 格式: "PASS: reason" | "FAIL: reason" | "BLOCKED: reason" | "SKIP: reason"
    """
    if dry_run:
        return True, "DRY_RUN — 跳過 Claude 呼叫"

    failure_count = 0
    for attempt in range(1, 4):
        logger.info(f"  任務嘗試 {attempt}/3: {task_text[:50]}")
        success, output = run_claude_task_wrapper(proj_dir, task_text)
        if not success:
            logger.warning(f"  Lobster 執行失敗: {output[:100]}")
            failure_count += 1
            continue

        result, reason = Inspector.inspect(proj_dir, task_text, output, failure_count)
        logger.info(f"  Inspector: {result} — {reason[:80]}")

        if result == "PASS":
            return True, f"PASS: {reason}"
        if result == "BLOCKED":
            # 發送 Telegram 警報
            send_telegram_alert(
                f"🚫 *Lobster 任務阻斷*\n\n"
                f"專案: `{proj_dir.name}`\n"
                f"任務: {task_text[:80]}\n"
                f"原因: {reason[:200]}\n\n"
                f"請人工介入後在 STATUS.md 或 TASK_BOARD.md 將 `[!]` 改為 `[ ]` 以恢復執行。"
            )
            return False, f"BLOCKED: {reason}"
        # result == "FAIL" → 重試
        failure_count += 1
        logger.warning(f"  驗證失敗 ({attempt}/3): {reason[:80]}")

    return False, f"FAIL: 連續 3 次驗證失敗"


def run_claude_task_wrapper(proj_dir: Path, task_text: str) -> tuple[bool, str]:
    """呼叫 Claude --print 執行任務（封装版）"""
    cmd = [
        str(CLAUDE_BIN), "--print", "--output-format", "text",
        "--max-tokens", str(MAX_TOKENS_PER_TASK),
        "--no-session-persistence",
        f"你是 AgentOS Lobster Engine。執行任務：**{task_text}**\n\n"
        f"執行後必須輸出 `✅ 任務完成：{task_text[:40]}` 或 `⚠️ 需要人工介入：原因`",
    ]
    try:
        result = subprocess.run(cmd, cwd=str(proj_dir), capture_output=True, text=True, timeout=TASK_TIMEOUT_SECONDS)
        output = result.stdout.strip()
        if result.returncode == 0:
            return True, output
        return False, f"EXIT_{result.returncode}: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)

# ── 設定 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (🦞 Lobster) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/ubuntu/agent-data/logs/lobster.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("Lobster")

HOME = Path("/home/ubuntu")
AGENT_DATA_ROOT = HOME / "agent-data"
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
CLAUDE_BIN = HOME / ".antigravity-ide-server/extensions/anthropic.claude-code-2.1.152-linux-arm64/resources/native-binary/claude"
TASK_BOARD = AGENT_DATA_ROOT / "TASK_BOARD.md"

# 每個任務執行後的冷卻時間（秒）
COOL_DOWN_SECONDS = 30

# 最大 Token 預算（避免爆量）
MAX_TOKENS_PER_TASK = 8000

# 任務超時（秒）- 避免模型卡死
TASK_TIMEOUT_SECONDS = 300

# ── 工具函數 ──────────────────────────────────────────────────────────────

def load_env():
    env_path = HOME / "agentmanager/.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env()

def get_pulse() -> dict:
    """讀取 swarm pulse 狀態"""
    for path in [
        Path("/dev/shm/leopardcat-swarm/pulse.json"),
        AGENT_DATA_ROOT / "runtime/pulse_snapshot.json",
    ]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
    return {}

def parse_todos(status_md: Path) -> list[dict]:
    """從 STATUS.md 解析 Todo 清單，返回未完成項目"""
    if not status_md.exists():
        return []
    
    todos = []
    content = status_md.read_text(encoding="utf-8")
    
    # 找 Todo 區段
    in_todo = False
    for line in content.splitlines():
        if re.match(r"^##\s+.*(Todo|TODO|Task|任務)", line, re.IGNORECASE):
            in_todo = True
            continue
        if in_todo and line.startswith("##"):
            break  # 遇到下一個 section 就停
        if in_todo:
            # 解析三種狀態
            m = re.match(r"^[-*]\s+\[([ x/])\]\s+(.+)", line)
            if m:
                status_char = m.group(1)
                task_text = m.group(2).strip()
                status_map = {" ": "todo", "x": "done", "/": "in_progress"}
                todos.append({
                    "status": status_map.get(status_char, "unknown"),
                    "text": task_text,
                    "raw_line": line,
                })
    
    return todos

def pick_next_task(todos: list[dict]) -> Optional[dict]:
    """選下一個未完成任務 (in_progress 優先，再取第一個 todo)"""
    in_progress = [t for t in todos if t["status"] == "in_progress"]
    if in_progress:
        return in_progress[0]
    pending = [t for t in todos if t["status"] == "todo"]
    if pending:
        return pending[0]
    return None

def mark_task_in_progress(status_md: Path, task: dict) -> bool:
    """在 STATUS.md 中將任務標記為 [/] 進行中"""
    content = status_md.read_text(encoding="utf-8")
    old_line = task["raw_line"]
    new_line = old_line.replace("[ ]", "[/]", 1)
    if old_line == new_line:
        return False
    status_md.write_text(content.replace(old_line, new_line, 1), encoding="utf-8")
    return True

def mark_task_done(status_md: Path, task: dict) -> bool:
    """在 STATUS.md 中將任務標記為 [x] 完成"""
    content = status_md.read_text(encoding="utf-8")
    # 匹配 [ ] 或 [/]
    old_line = task["raw_line"]
    new_line = re.sub(r"\[[ /]\]", "[x]", old_line, count=1)
    if old_line == new_line:
        return False
    status_md.write_text(content.replace(old_line, new_line, 1), encoding="utf-8")
    return True

def log_activity(status_md: Path, message: str):
    """在 STATUS.md 的 Activity Log 中插入一條記錄"""
    content = status_md.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- `{now}` 🦞 **[AUTO]** {message}"
    
    if "<!-- LOG_START -->" in content:
        content = content.replace(
            "<!-- LOG_START -->",
            f"<!-- LOG_START -->\n{entry}",
            1
        )
        status_md.write_text(content, encoding="utf-8")

def get_project_context(proj_name: str) -> str:
    """生成傳給 Claude 的任務上下文 prompt"""
    status_md = PROJECTS_DIR / proj_name / "STATUS.md"
    status_content = ""
    if status_md.exists():
        status_content = status_md.read_text(encoding="utf-8")[:3000]
    
    pulse = get_pulse()
    
    return f"""你是 AgentOS 自律執行器（Lobster Engine）。
你正在自主執行 **{proj_name}** 專案的任務。

## 當前 Swarm Pulse
```json
{json.dumps(pulse, indent=2, ensure_ascii=False)}
```

## 專案 STATUS.md
```markdown
{status_content}
```

## 核心規則
- 邏輯（代碼）留在 /home/ubuntu/{proj_name}/
- 資料（STATUS.md, memory/）留在 /home/ubuntu/agent-data/projects/{proj_name}/
- 完成任務後，在 STATUS.md 的 Activity Log 寫入一條記錄
- 不要詢問用戶，盡可能自主判斷並執行
- 如遇到需要人工確認的關鍵決策，在 STATUS.md 的 Blockers 區段留下說明後停止

"""

def run_claude_task(proj_name: str, task: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    用 Claude Code CLI --print 模式執行一個任務。
    返回 (成功與否, 輸出摘要)
    """
    proj_dir = HOME / proj_name
    if not proj_dir.exists():
        logger.warning(f"專案目錄不存在: {proj_dir}")
        return False, "PROJECT_DIR_NOT_FOUND"
    
    context = get_project_context(proj_name)
    prompt = f"""{context}

## 你現在的任務
請執行以下任務（這是從 STATUS.md Todo List 中自動選取的）：

**{task['text']}**

請：
1. 分析這個任務需要做什麼
2. 實際執行（修改代碼/建立文件/測試等）
3. 驗證結果
4. 最後輸出一句「✅ 任務完成：[任務名稱]」或「⚠️ 需要人工介入：[原因]」
"""
    
    if dry_run:
        logger.info(f"[DRY RUN] 會在 {proj_dir} 執行: {task['text'][:80]}")
        return True, "DRY_RUN"
    
    cmd = [
        str(CLAUDE_BIN),
        "--print",
        "--output-format", "text",
        "--max-tokens", str(MAX_TOKENS_PER_TASK),
        "--no-session-persistence",
        prompt,
    ]
    
    logger.info(f"🚀 開始執行任務: {task['text'][:60]}...")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SECONDS,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(proj_dir)},
        )
        
        output = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if result.returncode == 0:
            logger.info(f"✅ 任務執行成功 (exit 0)")
            return True, output[-1000:]  # 只取最後 1000 字
        else:
            logger.error(f"❌ 任務執行失敗 (exit {result.returncode}): {stderr[:200]}")
            return False, f"EXIT_{result.returncode}: {stderr[:200]}"
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ 任務超時 ({TASK_TIMEOUT_SECONDS}s)")
        return False, "TIMEOUT"
    except Exception as e:
        logger.error(f"💥 執行異常: {e}")
        return False, str(e)


# ── 主要邏輯 ──────────────────────────────────────────────────────────────

def get_all_projects_from_board() -> list[tuple[str, list[dict]]]:
    """
    從中央 TASK_BOARD.md 讀取任務。
    返回 [(proj_name, [todo_dict, ...]), ...]
    """
    if not TASK_BOARD.exists():
        return []
    
    content = TASK_BOARD.read_text(encoding="utf-8")
    results = []
    current_proj = None
    current_todos = []
    
    for line in content.splitlines():
        # 專案標題行，例如 "### 📦 youtube-ai-manager" 或 "### ✅ beauty-pk"
        proj_m = re.match(r"^###\s+[\S]+\s+([\w\-]+)\s*$", line)
        if proj_m:
            if current_proj and current_todos:
                results.append((current_proj, current_todos))
            current_proj = proj_m.group(1)
            current_todos = []
            continue
        
        if current_proj:
            m = re.match(r"^[-*]\s+\[([ x/])\]\s+(.+)", line)
            if m:
                status_char = m.group(1)
                task_text = m.group(2).strip()
                status_map = {" ": "todo", "x": "done", "/": "in_progress"}
                current_todos.append({
                    "status": status_map.get(status_char, "unknown"),
                    "text": task_text,
                    "raw_line": line,
                    "source": "board",
                })
    
    if current_proj and current_todos:
        results.append((current_proj, current_todos))
    
    return results


def mark_board_task(task_text: str, new_status: str):
    """
    在 TASK_BOARD.md 中更新特定任務的狀態。
    new_status: 'in_progress' | 'done' | 'blocked'
    """
    if not TASK_BOARD.exists():
        return
    
    status_map = {"in_progress": "/", "done": "x", "todo": " ", "blocked": "!"}
    new_mark = status_map.get(new_status, " ")
    
    content = TASK_BOARD.read_text(encoding="utf-8")
    # 找到這個任務行並替換狀態標記
    pattern = re.compile(r"(^[-*]\s+\[)[ x/!](\]\s+" + re.escape(task_text) + r")", re.MULTILINE)
    new_content = pattern.sub(rf"\g<1>{new_mark}\g<2>", content, count=1)
    if new_content != content:
        TASK_BOARD.write_text(new_content, encoding="utf-8")


def get_all_projects() -> list[str]:
    """取得所有有 STATUS.md 的專案"""
    projects = []
    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        if (d / "STATUS.md").exists():
            projects.append(d.name)
    return sorted(projects)

def process_project(proj_name: str, dry_run: bool = False) -> bool:
    """
    處理單個專案：找任務、執行、更新狀態。
    返回 True 表示有執行到任務。
    """
    status_md = PROJECTS_DIR / proj_name / "STATUS.md"
    if not status_md.exists():
        return False
    
    todos = parse_todos(status_md)
    task = pick_next_task(todos)
    
    if not task:
        logger.info(f"📭 [{proj_name}] 沒有待處理任務")
        return False
    
    logger.info(f"📌 [{proj_name}] 選定任務: {task['text'][:60]}")
    
    # 標記為進行中
    if task["status"] == "todo":
        mark_task_in_progress(status_md, task)
        task["raw_line"] = task["raw_line"].replace("[ ]", "[/]", 1)
    
    # 執行任務
    success, output = run_with_inspector(HOME / proj_name, task["text"], dry_run)
    
    if success:
        mark_task_done(status_md, task)
        log_activity(status_md, f"完成任務：{task['text'][:60]} ({output})")
        logger.info(f"🎉 [{proj_name}] 任務完成！")
    else:
        # 失敗：保持 [/] 狀態，但記錄錯誤
        log_activity(status_md, f"任務執行失敗（{output[:120]}）")
        logger.warning(f"⚠️ [{proj_name}] 任務失敗，保留進行中狀態等待人工介入")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description="🦞 Lobster Engine - AgentOS 自律任務執行器"
    )
    parser.add_argument("--loop", action="store_true", help="持續迴圈執行（永動機）")
    parser.add_argument("--project", "-p", type=str, help="只處理指定專案")
    parser.add_argument("--dry-run", action="store_true", help="只顯示任務，不實際執行")
    parser.add_argument("--cool-down", type=int, default=COOL_DOWN_SECONDS, help="每次任務後冷卻秒數")
    args = parser.parse_args()
    
    # 優雅關閉
    running = [True]
    def handle_signal(sig, frame):
        logger.info("🛑 收到停止信號，完成當前任務後退出...")
        running[0] = False
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    logger.info("🦞 Lobster Engine 啟動！")
    
    iteration = 0
    while running[0]:
        iteration += 1
        logger.info(f"━━━ 迭代 #{iteration} ━━━")
        
        did_work = False
        
        if args.project:
            did_work = process_project(args.project, args.dry_run)
        elif TASK_BOARD.exists():
            # 優先讀中央看板
            board_projects = get_all_projects_from_board()
            pending_found = False
            for proj_name, todos in board_projects:
                if not running[0]:
                    break
                task = pick_next_task(todos)
                if not task:
                    continue
                
                logger.info(f"📌 [BOARD→{proj_name}] 選定任務: {task['text'][:60]}")
                
                # 在 TASK_BOARD 標記為進行中
                if task["status"] == "todo":
                    mark_board_task(task["text"], "in_progress")
                
                # 執行任務
                success, output = run_with_inspector(HOME / proj_name, task["text"], args.dry_run)
                
                # 在 TASK_BOARD 更新狀態
                if success:
                    mark_board_task(task["text"], "done")
                    # 同步回各專案的 STATUS.md
                    status_md = PROJECTS_DIR / proj_name / "STATUS.md"
                    if status_md.exists():
                        log_activity(status_md, f"完成任務：{task['text'][:60]} ({output})")
                    logger.info(f"🎉 [{proj_name}] 任務完成！")
                else:
                    if "BLOCKED:" in output:
                        mark_board_task(task["text"], "blocked")
                    else:
                        mark_board_task(task["text"], "in_progress")  # 保留 [/] 狀態
                    # 同步回各專案的 STATUS.md
                    status_md = PROJECTS_DIR / proj_name / "STATUS.md"
                    if status_md.exists():
                        log_activity(status_md, f"任務執行失敗（{output[:120]}）")
                    logger.warning(f"⚠️ [{proj_name}] 任務失敗，保留狀態: {output[:100]}")
                
                did_work = True
                pending_found = True
                break  # 一次只做一個任務
            
            if not pending_found:
                logger.info("📭 TASK_BOARD 中所有任務已完成")
        else:
            # 退回掃描各 STATUS.md
            projects = get_all_projects()
            logger.info(f"📂 掃描 {len(projects)} 個專案...")
            for proj in projects:
                if not running[0]:
                    break
                if process_project(proj, args.dry_run):
                    did_work = True
                    break
        
        if not args.loop:
            break
        
        if not did_work:
            # 所有專案都沒有待辦任務，進入休眠
            sleep_sec = args.cool_down * 3  # 空閒時睡更久
            logger.info(f"😴 所有任務已完成，休眠 {sleep_sec}s 後重新掃描...")
        else:
            sleep_sec = args.cool_down
            logger.info(f"⏳ 冷卻 {sleep_sec}s...")
        
        # 分段睡眠，可響應停止信號
        for _ in range(sleep_sec):
            if not running[0]:
                break
            time.sleep(1)
    
    logger.info("🦞 Lobster Engine 停止。")

if __name__ == "__main__":
    main()
