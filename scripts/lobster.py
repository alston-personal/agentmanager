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

# 核心執行引擎選擇 (claude | agy)
def _load_env_early():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

_load_env_early()
ACTIVE_ENGINE = os.getenv("LOBSTER_ENGINE", "claude")


# ── AgentOS 角色路由配置 ───────────────────────────────────────────────────
import yaml

def get_target_output_path(proj_name: str, proj_dir: Path) -> Path:
    """
    路由協議：根據專案名稱決定實際的輸出目標路徑。
    """
    # 如果是 zeus-writer 相關專案
    if "zeus-writer" in str(proj_dir) or (HOME / "zeus-writer" / proj_name).exists():
        # 優先檢查是否有獨立的作品資料夾
        work_root = HOME / "zeus-writer" / proj_name
        if work_root.exists():
            target = work_root / "正文"
            if target.exists():
                return target
            # 如果正文資料夾不存在，則建立它
            target.mkdir(parents=True, exist_ok=True)
            return target

    # 預設回退到專案根目錄
    return proj_dir

def get_agent_persona(task_text: str) -> tuple[str, str, str]:
    """
    根據任務內容路由至對應的寫作角色。
    返回: (角色名稱, System Prompt, SOP)
    """
    persona_path = Path("/home/ubuntu/zeus-writer/writing_persona.yaml")
    if not persona_path.exists():
        return "General", "You are a helpful assistant.", "1. Read context\n2. Execute task\n3. Verify output\n4. Report success"

    try:
        with open(persona_path, "r", encoding="utf-8") as f:
            personas = yaml.safe_load(f)

        # 角色 SOP 定義
        SOPs = {
            "writer": "1. [Context Analysis]: Use `Read` to check the outline and previous chapters in the target directory.\n2. [Drafting]: Use `Write` to create the new chapter file in the target directory.\n3. [Self-Verification]: Use `Read` on the file you just wrote to ensure it meets the style guidelines.\n4. [Completion]: Output: ✅ 任務完成：[Task Name] - File saved to [Path].",
            "editor": "1. [Review]: Use `Read` to analyze the target file's logic and flow.\n2. [Refinement]: Use `Edit` to modify the content directly in the file.\n3. [Verification]: Use `Read` to verify the changes.\n4. [Completion]: Output: ✅ 校對完成：[Task Name] - File updated at [Path].",
            "illustrator": "1. [Visual Analysis]: Analyze the scene description in the task.\n2. [Prompt Engineering]: Create a detailed Image Prompt.\n3. [Output]: Write the prompt to the target directory as a .md file.\n4. [Completion]: Output: ✅ 視覺方案完成：[Task Name] - Path: [Path].",
            "marketer": "1. [Trend Analysis]: Analyze the target audience.\n2. [Hook Creation]: Draft high-impact hooks for social media.\n3. [Output]: Write the marketing copy to the target directory.\n4. [Completion]: Output: ✅ 行銷方案完成：[Task Name].",
            "arbitrator": "1. [Comparative Review]: Read multiple versions of the same chapter.\n2. [Final Decision]: Select the best parts and merge them using `Edit`.\n3. [Completion]: Output: ✅ 定稿完成：[Task Name].",
            "general": "1. [Analyze]: Understand the requirement.\n2. [Execute]: Use `Read`/`Write`/`Edit` tools to perform the task.\n3. [Verify]: Check the result.\n4. [Completion]: Output: ✅ 任務完成：[Task Name]."
        }

        task_lower = task_text.lower()
        if any(k in task_lower for k in ["撰寫", "寫作", "正文", "章節", "創作"]):
            role_key = "writer"
        elif any(k in task_lower for k in ["審核", "校對", "編輯", "修改", "邏輯"]):
            role_key = "editor"
        elif any(k in task_lower for k in ["封面", "插畫", "Image Prompt", "視覺"]):
            role_key = "illustrator"
        elif any(k in task_lower for k in ["行銷", "爆點", "傳播", "讀者"]):
            role_key = "marketer"
        elif any(k in task_lower for k in ["仲裁", "定稿", "決定"]):
            role_key = "arbitrator"
        else:
            role_key = "general"

        role_data = personas.get(role_key, {}) if role_key != "general" else {}
        return role_data.get("name", role_key.capitalize()), role_data.get("system_prompt", ""), SOPs.get(role_key)

    except Exception as e:
        logger.error(f"載入 Persona 失敗: {e}")

    return "General", "You are a helpful assistant.", "1. Analyze\n2. Execute\n3. Verify\n4. Report"

def verify_physical_output(proj_dir: Path, task_text: str, output: str, target_dir: Optional[Path] = None) -> bool:
    """
    物理驗證：檢查檔案系統是否真的有新檔案產生或內容增加。
    如果提供 target_dir，則僅檢查該目錄下的變動。
    """
    if "DRY_RUN" in output:
        return True

    # 如果任務包含「撰寫」且輸出宣稱完成，但沒有任何 .md 檔案變動，則判定為失敗
    if any(k in task_text for k in ["撰寫", "寫作", "創作"]):
        # 檢查最近 5 分鐘內是否有 .md 檔案被修改/建立
        now = time.time()
        search_dir = target_dir if target_dir else proj_dir
        modified_files = []
        try:
            for f in search_dir.rglob("*.md"):
                if (now - f.stat().st_mtime) < 600:
                    modified_files.append(f)
        except Exception as e:
            logger.error(f"物理驗證掃描失敗: {e}")
            return False

        if not modified_files:
            return False
    return True


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

    ⚠️ 重要行為：
    - TIMEOUT → 立刻 SKIP（不重試，避免 3×5min=15min 卡在同一任務）
    - 3 次 FAIL → BLOCKED（發 Telegram + 跳下一個任務）
    """
    if dry_run:
        return True, "DRY_RUN — 跳過 Claude 呼叫"

    failure_count = 0
    for attempt in range(1, 4):
        logger.info(f"  任務嘗試 {attempt}/3: {task_text[:50]}")
        success, output = run_claude_task_wrapper(proj_dir, task_text)
        if not success:
            logger.warning(f"  Lobster 執行失敗: {output[:100]}")
            # TIMEOUT 立刻 SKIP，不浪費時間重試
            if output == "TIMEOUT":
                msg = f"任務逾時（{TASK_TIMEOUT_SECONDS}s），跳過此任務並標記為阻斷"
                send_telegram_alert(
                    f"⏰ *Lobster 任務逾時 BLOCKED*\n\n"
                    f"專案: `{proj_dir.name}`\n"
                    f"任務: {task_text[:80]}\n"
                    f"原因: 執行時間超過 {TASK_TIMEOUT_SECONDS} 秒。\n\n"
                    f"已自動標記為阻斷，請人工介入排除問題後，將 TASK_BOARD.md 或 STATUS.md 中的 `[!]` 改回 `[ ]` 以恢復執行。"
                )
                logger.warning(f"  🚫 BLOCKED（TIMEOUT）: {msg}")
                return False, f"BLOCKED: {msg}"
            failure_count += 1
            continue

        if Inspector is None:
            # Inspector 未載入，信任輸出直接 PASS
            logger.warning("  Inspector 未載入，預設信任輸出")
            return True, "PASS: Inspector 未載入，預設信任"

        result, reason = Inspector.inspect(proj_dir, task_text, output, failure_count)
        logger.info(f"  Inspector: {result} — {reason[:80]}")

        if result == "PASS":
            # 實施物理驗證：如果是寫作任務，必須檢查是否有檔案變動
            # 獲取路由目標路徑
            target_dir = get_target_output_path(proj_dir.name, proj_dir)
            if not verify_physical_output(proj_dir, task_text, output, target_dir=target_dir):
                logger.warning(f"  🚫 物理驗證失敗：任務宣稱完成但無實體檔案產出（幻覺完成）")
                return False, f"FAIL: 幻覺完成，缺乏實體產出"
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
        if result == "SKIP":
            return True, f"SKIP: {reason}"
        # result == "FAIL" → 重試
        failure_count += 1
        logger.warning(f"  驗證失敗 ({attempt}/3): {reason[:80]}")

    # 連續 3 次失敗 → 升級為 BLOCKED，發通知，跳過繼續
    blocked_msg = f"連續 3 次驗證失敗，標記為阻斷，自動跳過繼續下一個任務"
    send_telegram_alert(
        f"🚫 *Lobster 任務 3 次失敗→BLOCKED*\n\n"
        f"專案: `{proj_dir.name}`\n"
        f"任務: {task_text[:80]}\n"
        f"已自動跳過，請檢查 TASK_BOARD.md 的 [!] 任務。"
    )
    logger.warning(f"  🚫 BLOCKED: {blocked_msg}")
    return False, f"BLOCKED: {blocked_msg}"


def run_claude_task_wrapper(proj_dir: Path, task_text: str) -> tuple[bool, str]:
    """呼叫指定引擎執行任務（封装版）"""
    # ── AgentOS 角色路由 ──
    role_name, system_prompt, sop = get_agent_persona(task_text)
    target_dir = get_target_output_path(proj_dir.name, proj_dir)
    logger.info(f"⚡ [Role Route] 任務路由至角色: {role}, 目標路徑: {target_dir}")

    # ── 本地確定性任務攔截路由 (Local interceptors registry) ──
    port_match = re.search(r"檢查連接埠\s+(\d+)", task_text)

    if port_match:
        port = port_match.group(1)
        cmd = ["python3", "/home/ubuntu/agentmanager/scripts/local_port_checker.py", str(port)]
        logger.info(f"⚡ [Local Route] 偵測到連接埠 {port} 檢查任務，自動路由至本地執行器（0 Token 消耗）。")
    elif ACTIVE_ENGINE == "agy":
        cmd = [
            "agy", "run", "--task", task_text, "--workspace", str(proj_dir)
        ]
    else:
        # 注入角色 Persona, SOP 以及路徑約束
        full_prompt = (
            f"{system_prompt}\n\n"
            f"你是 AgentOS Lobster Engine 調度之 {role}。\n"
            f"PRIMARY_OUTPUT_DIRECTORY: {target_dir}\n\n"
            f"## 執行 SOP:\n{sop}\n\n"
            f"## 任務內容：\n**{task_text}**\n\n"
            f"執行後必須輸出 `✅ 任務完成：{task_text[:40]}` 或 `⚠️ 需要人工介入：原因`"
        )
        cmd = [
            str(get_claude_bin()),
            "--output-format", "text",
            "--effort", "low",
            full_prompt,
        ]


    
    # 建立固定的任務執行日誌檔
    slug = re.sub(r"[^\w\-]", "-", task_text)
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = slug[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path("/home/ubuntu/agent-data/logs/tasks")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{timestamp}_{proj_dir.name}_{slug}.log"

    log_content = [
        "=========================================",
        "🦞 Lobster Engine Task Execution Log",
        "=========================================",
        f"Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Project:     {proj_dir.name} ({proj_dir})",
        f"Task:        {task_text}",
        f"Command:     {' '.join(cmd)}",
        "=========================================",
        "",
    ]

    try:
        result = subprocess.run(cmd, cwd=str(proj_dir), capture_output=True, text=True, timeout=TASK_TIMEOUT_SECONDS)
        output = result.stdout.strip()
        stderr = result.stderr.strip()
        
        log_content.extend([
            "--- STDOUT ---",
            output,
            "",
            "--- STDERR ---",
            stderr,
            "",
            f"Exit Code:   {result.returncode}",
        ])
        success = (result.returncode == 0)
        ret_val = (success, output if success else f"EXIT_{result.returncode}: {stderr[:200]}")
    except subprocess.TimeoutExpired:
        log_content.extend([
            "--- ERROR ---",
            f"Timeout of {TASK_TIMEOUT_SECONDS} seconds expired."
        ])
        ret_val = (False, "TIMEOUT")
    except Exception as e:
        log_content.extend([
            "--- ERROR ---",
            str(e)
        ])
        ret_val = (False, str(e))
    finally:
        try:
            log_file.write_text("\n".join(log_content), encoding="utf-8")
            logger.info(f"💾 任務執行日誌已寫入: {log_file}")
        except Exception as log_err:
            logger.error(f"無法寫入任務日誌檔: {log_err}")

    return ret_val

# ── 設定 ─────────────────────────────────────────────────────────────────
# Determine home and data root dynamically
HOME = Path.home()
DATA_ROOT_ENV = os.getenv("AGENT_DATA_ROOT") or os.getenv("AGENT_DATA_DIR")
if DATA_ROOT_ENV:
    AGENT_DATA_ROOT = Path(DATA_ROOT_ENV).expanduser()
else:
    AGENT_DATA_ROOT = HOME / "agent-data"

log_dir = AGENT_DATA_ROOT / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "lobster.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (🦞 Lobster) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("Lobster")

PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

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

def get_claude_bin() -> Path:
    return _find_claude_bin()

TASK_BOARD = AGENT_DATA_ROOT / "TASK_BOARD.md"

# 每個任務執行後的冷卻時間（秒）
COOL_DOWN_SECONDS = 30

# 最大 Token 預算（避免爆量）
MAX_TOKENS_PER_TASK = 8000

# 任務超時（秒）- 避免模型卡死
TASK_TIMEOUT_SECONDS = 300

# ── 工具函數 ──────────────────────────────────────────────────────────────

def load_env():
    # Load .env relative to scripts folder (parent of scripts is the project root)
    env_path = Path(__file__).resolve().parent.parent / ".env"
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
    try:
        import sys as _sys
        root = str(Path(__file__).resolve().parents[1])
        if root not in _sys.path:
            _sys.path.insert(0, root)
        from agent_core.platform import get_platform_driver
        driver = get_platform_driver(project_root=Path(__file__).resolve().parents[1], data_root=AGENT_DATA_ROOT)
        paths = [
            driver.volatile_state_dir() / "pulse.json",
            driver.persistent_state_dir() / "pulse_snapshot.json",
        ]
    except Exception:
        paths = [AGENT_DATA_ROOT / "runtime" / "pulse_snapshot.json"]

    for path in paths:
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
            # 解析四種狀態（含 [!] blocked）
            m = re.match(r"^[-*]\s+\[([ x/!])\]\s+(.+)", line)
            if m:
                status_char = m.group(1)
                task_text = m.group(2).strip()
                status_map = {" ": "todo", "x": "done", "/": "in_progress", "!": "blocked"}
                todos.append({
                    "status": status_map.get(status_char, "unknown"),
                    "text": task_text,
                    "raw_line": line,
                })
    
    return todos

def pick_next_task(todos: list[dict]) -> Optional[dict]:
    """選下一個未完成任務 (in_progress 優先，再取第一個 todo）。跳過 blocked 任務。"""
    in_progress = [t for t in todos if t["status"] == "in_progress"]
    if in_progress:
        return in_progress[0]
    pending = [t for t in todos if t["status"] == "todo"]  # blocked 不在內
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
        
        # 自動執行日誌滾動歸檔
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from archive_status_logs import archive_project_status
            archive_project_status(status_md.parent.name)
        except Exception as e:
            logger.warning(f"自動歸檔日誌失敗: {e}")


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
- 邏輯（代碼）留在 {HOME}/{proj_name}/
- 資料（STATUS.md, memory/）留在 {AGENT_DATA_ROOT}/projects/{proj_name}/
- 完成任務後，在 STATUS.md 的 Activity Log 寫入一條記錄
- 不要詢問用戶，盡可能自主判斷並執行
- 如遇到需要人工確認的關鍵決策，在 STATUS.md 的 Blockers 區段留下說明後停止

"""

def run_claude_task(proj_name: str, task: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    用指定引擎執行一個任務。
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
    
    if ACTIVE_ENGINE == "agy":
        cmd = [
            "agy", "run", "--task", task['text'], "--workspace", str(proj_dir),
            "--prompt", prompt
        ]
    else:
        cmd = [
            str(get_claude_bin()),
            "--bare",
            "--print",
            "--output-format", "text",
            "--max-tokens", str(MAX_TOKENS_PER_TASK),
            "--dangerously-skip-permissions",
            prompt,
        ]
    
    logger.info(f"🚀 開始執行任務 ({ACTIVE_ENGINE}): {task['text'][:60]}...")
    
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
            m = re.match(r"^[-*]\s+\[([ x/!])\]\s+(.+)", line)
            if m:
                status_char = m.group(1)
                task_text = m.group(2).strip()
                status_map = {" ": "todo", "x": "done", "/": "in_progress", "!": "blocked"}
                current_todos.append({
                    "status": status_map.get(status_char, "unknown"),
                    "text": task_text,
                    "raw_line": line,
                    "source": "board",
                })
    
    if current_proj and current_todos:
        results.append((current_proj, current_todos))
    
    return results


def mark_board_task(proj_name: str, task_text: str, new_status: str, current_status: Optional[str] = None):
    """
    在 TASK_BOARD.md 中的指定專案區段更新特定任務的狀態。
    new_status: 'in_progress' | 'done' | 'blocked' | 'todo'
    """
    if not TASK_BOARD.exists():
        return
    
    status_map = {"in_progress": "/", "done": "x", "todo": " ", "blocked": "!"}
    new_mark = status_map.get(new_status, " ")
    
    content = TASK_BOARD.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    in_target_proj = False
    updated = False
    
    for i, line in enumerate(lines):
        proj_m = re.match(r"^###\s+[\S]+\s+([\w\-]+)\s*$", line)
        if proj_m:
            if in_target_proj:
                break
            if proj_m.group(1) == proj_name:
                in_target_proj = True
            continue
            
        if in_target_proj:
            # 匹配狀態欄和任務描述
            m = re.match(r"^([-*]\s+\[)([ x/!])(\]\s+)" + re.escape(task_text) + r"\s*$", line)
            if m:
                status_char = m.group(2)
                if current_status:
                    curr_map = {"todo": " ", "done": "x", "in_progress": "/", "blocked": "!"}
                    if curr_map.get(current_status) != status_char:
                        continue
                
                lines[i] = f"{m.group(1)}{new_mark}{m.group(3)}{task_text}"
                updated = True
                break
                
    if updated:
        TASK_BOARD.write_text("\n".join(lines) + "\n", encoding="utf-8")



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
    global ACTIVE_ENGINE
    parser = argparse.ArgumentParser(
        description="🦞 Lobster Engine - AgentOS 自律任務執行器"
    )
    parser.add_argument("--loop", action="store_true", help="持續迴圈執行（永動機）")
    parser.add_argument("--project", "-p", type=str, help="只處理指定專案")
    parser.add_argument("--dry-run", action="store_true", help="只顯示任務，不實際執行")
    parser.add_argument("--cool-down", type=int, default=COOL_DOWN_SECONDS, help="每次任務後冷卻秒數")
    parser.add_argument("--engine", choices=["claude", "agy"], default=ACTIVE_ENGINE, help="指定執行的 AI 引擎 (claude | agy)")
    args = parser.parse_args()

    ACTIVE_ENGINE = args.engine
    
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
                    mark_board_task(proj_name, task["text"], "in_progress", current_status="todo")
                
                # 執行任務
                success, output = run_with_inspector(HOME / proj_name, task["text"], args.dry_run)
                
                # 在 TASK_BOARD 更新狀態
                if success:
                    mark_board_task(proj_name, task["text"], "done", current_status="in_progress")
                    # 同步回各專案的 STATUS.md
                    status_md = PROJECTS_DIR / proj_name / "STATUS.md"
                    if status_md.exists():
                        log_activity(status_md, f"完成任務：{task['text'][:60]} ({output})")
                    logger.info(f"🎉 [{proj_name}] 任務完成！")
                else:
                    if "BLOCKED:" in output:
                        # BLOCKED → 標記 [!]，跳過繼續（不停機）
                        mark_board_task(proj_name, task["text"], "blocked", current_status="in_progress")
                        logger.warning(f"🚫 [{proj_name}] 任務 BLOCKED，標記 [!] 並繼續下一個")
                    elif "SKIP:" in output:
                        # SKIP（TIMEOUT 等）→ 標記回 [ ] 等下次，跳過繼續
                        mark_board_task(proj_name, task["text"], "todo", current_status="in_progress")
                        logger.warning(f"⏭️ [{proj_name}] 任務 SKIP，重置為 [ ] 等下次")
                    else:
                        mark_board_task(proj_name, task["text"], "in_progress", current_status="in_progress")  # 保留 [/] 狀態
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
