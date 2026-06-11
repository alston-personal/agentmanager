import os
import subprocess
import logging
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler, CommandHandler, filters
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add logic root to path to import service_utils
LOGIC_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(LOGIC_ROOT))
from scripts.service_utils import setup_locking, handle_signals, init_service_logging

load_dotenv()

# --- 配置中心 ---
def get_env_secret(key, default=None):
    val = os.getenv(key, default)
    if val and "[REDACTED" in val:
        # Try to find in data layer
        data_root = os.getenv("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))
        data_env = Path(data_root) / "secrets/global.env"
        if data_env.exists():
            with open(data_env, "r") as f:
                for line in f:
                    if line.startswith(f"{key}="):
                        return line.split("=")[1].strip()
    return val

AUTHORIZED_USER_ID = get_env_secret("TELEGRAM_CHANNEL_ID")
PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
AGENT_DATA_ROOT = os.getenv("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))
GEMINI_API_KEY = get_env_secret("GEMINI_API_KEY")
KNOWLEDGE_ROOT = os.getenv("KNOWLEDGE_ROOT", os.path.expanduser("~/.gemini/antigravity/knowledge"))
MEMORY_ROOT = os.path.join(AGENT_DATA_ROOT, "memory")
SYSTEM_ID_PATH = os.path.join(PROJECT_ROOT, ".agent/SYSTEM_IDENTITY.md")
WORKFLOW_RUNNER = os.path.join(PROJECT_ROOT, "scripts", "run_workflow.py")
DATA_DASHBOARD_PATH = os.path.join(AGENT_DATA_ROOT, "DASHBOARD.md")
SESSION_SYNC_PATH = os.path.join(AGENT_DATA_ROOT, "memory", "session_sync.md")
TELEGRAM_SESSION_DIR = os.path.join(AGENT_DATA_ROOT, "memory", "telegram_sessions")
SKILLS_ROOT = os.path.join(PROJECT_ROOT, ".agent", "skills")

MODEL_PREFERENCES = [
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash"
]

logger = init_service_logging(Path(AGENT_DATA_ROOT) / "logs" / "tg_bridge.log", "TGBridge")

# --- 核心工具 (Antigravity Agent 的感官與手腳) ---

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def sanitize_text(text: str) -> str:
    if not text:
        return ""
    secret_values = [
        os.getenv("GEMINI_API_KEY"),
        os.getenv("TELEGRAM_BOT_TOKEN"),
        os.getenv("TG_BOT_SUNLAKE_CC_TOKEN"),
        os.getenv("N8N_API_KEY"),
    ]
    sanitized = text
    for secret in secret_values:
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


def ensure_parent_dir(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def append_markdown_log(path: str, header: str, body: str):
    ensure_parent_dir(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"\n## {header}\n{body}\n")


def sync_session_event(source: str, user_text: str, agent_text: str = "", metadata: dict | None = None):
    timestamp = utc_now()
    meta = metadata or {}
    meta_lines = "\n".join([f"- **{key}**: {value}" for key, value in meta.items()]) if meta else ""
    body = (
        f"- **time**: {timestamp}\n"
        f"- **source**: {source}\n"
        f"- **user_chars**: {len(user_text or '')}\n"
        f"- **agent_chars**: {len(agent_text or '')}\n"
        f"{meta_lines}\n"
    )
    append_markdown_log(SESSION_SYNC_PATH, f"Session Event @ {timestamp}", body)


def persist_telegram_transcript(chat_id: str, user_text: str, agent_text: str = ""):
    transcript_path = os.path.join(TELEGRAM_SESSION_DIR, f"{chat_id}.md")
    body = (
        f"- **time**: {utc_now()}\n"
        f"- **user**:\n\n{sanitize_text(user_text)}\n\n"
        f"- **agent**:\n\n{sanitize_text(agent_text) or '(pending)'}\n"
    )
    append_markdown_log(transcript_path, f"Telegram Exchange @ {utc_now()}", body)

def read_system_identity():
    """讀取系統極終設定與身份核心 (SYSTEM_IDENTITY.md)。包含絕對不能跑偏的終極原則。"""
    try:
        if os.path.exists(SYSTEM_ID_PATH):
            with open(SYSTEM_ID_PATH, "r") as f: return f.read()
        return "系統身份檔案缺失。"
    except Exception as e: return f"讀取失敗: {e}"

def read_dual_layer_memory():
    """讀取雙層記憶 (SHORT_TERM.md, LONG_TERM.md)，了解當前任務與歷史進度。"""
    try:
        st, lt = "", ""
        st_p = os.path.join(AGENT_DATA_ROOT, "memory", "SHORT_TERM.md")
        lt_p = os.path.join(AGENT_DATA_ROOT, "memory", "LONG_TERM.md")
        if os.path.exists(st_p):
            with open(st_p, "r") as f: st = f.read()
        if os.path.exists(lt_p):
            with open(lt_p, "r") as f: lt = f.read()
        session_sync = ""
        if os.path.exists(SESSION_SYNC_PATH):
            with open(SESSION_SYNC_PATH, "r", encoding="utf-8") as f:
                session_sync = f.read()[-4000:]
        return f"【短期記憶】:\n{st}\n\n【長期記憶】:\n{lt}\n\n【Session Sync】:\n{session_sync}"
    except Exception as e: return f"記憶讀取失敗: {e}"

def list_knowledge_topics():
    """檢索全域知識庫。"""
    try:
        if not os.path.exists(KNOWLEDGE_ROOT): return "知識庫尚未初始化。"
        return "可用知識主題：\n" + "\n".join([f"- {t}" for t in os.listdir(KNOWLEDGE_ROOT)])
    except Exception as e: return f"失敗: {e}"

def read_knowledge_item(topic_name: str):
    """讀取特定知識主題內容。"""
    try:
        p = os.path.join(KNOWLEDGE_ROOT, topic_name, "metadata.json")
        res = ""
        if os.path.exists(p):
            with open(p, "r") as f: res += f"摘要：{json.load(f).get('Summary')}\n"
        return res or "無內容。"
    except: return "讀取失敗。"

def list_projects_status():
    """讀取資料層 DASHBOARD.md 看板。"""
    try:
        with open(DATA_DASHBOARD_PATH, "r") as f: return f.read()
    except Exception as e: return f"看板解析失敗: {e}"


def list_skill_topics():
    """列出可用技能主題。"""
    try:
        if not os.path.isdir(SKILLS_ROOT):
            return "技能庫不存在。"
        skills = sorted(
            p.name for p in Path(SKILLS_ROOT).iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        return "可用技能：\n" + "\n".join([f"- {name}" for name in skills])
    except Exception as e:
        return f"技能檢索失敗: {e}"


def read_skill_guide(skill_name: str):
    """讀取指定技能的 SKILL.md。"""
    try:
        skill_path = Path(SKILLS_ROOT) / skill_name / "SKILL.md"
        if not skill_path.exists():
            return f"找不到技能說明：{skill_name}"
        return skill_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"技能讀取失敗: {e}"

def run_system_workflow(workflow_name: str):
    """執行自動化工作流。"""
    try:
        res = subprocess.run(
            ["python3", WORKFLOW_RUNNER, workflow_name],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=30,
        )
        return res.stdout if res.returncode == 0 else f"錯誤: {res.stderr}"
    except Exception as e: return f"例外: {e}"


def run_agy_task(project_name: str, task_text: str) -> str:
    """
    呼叫 Antigravity CLI (agy) 在指定的專案目錄下執行自主變更、代碼修改或單元測試任務。
    這可以讓你直接替專案修復 Bug、編寫程式碼或執行驗證。
    """
    PROJECT_MAP = {
        "moltbot": "/home/ubuntu/moltbot",
        "openclaw": "/home/ubuntu/openclaw",
        "agentmanager": "/home/ubuntu/agentmanager",
        "leopardcat-tarot": "/home/ubuntu/leopardcat-tarot",
        "zeus-writer": "/home/ubuntu/zeus-writer",
        "youtube-ai-manager": "/home/ubuntu/youtube-ai-manager",
        "y2helper": "/home/ubuntu/y2helper",
        "beauty-pk": "/home/ubuntu/beauty-pk"
    }
    proj_dir = PROJECT_MAP.get(project_name)
    if not proj_dir:
        proj_dir = f"/home/ubuntu/{project_name}"
    
    if not os.path.exists(proj_dir):
        return f"錯誤：找不到專案 {project_name} 的路徑 {proj_dir}。"
        
    try:
        res = subprocess.run(
            ["agy", "run", "--task", task_text, "--workspace", proj_dir],
            capture_output=True,
            text=True,
            timeout=300
        )
        output = res.stdout if res.returncode == 0 else f"執行失敗：{res.stderr or res.stdout}"
        return output
    except Exception as e:
        return f"執行異常：{e}"


def list_available_workflows():
    """列出目前可用的 slash workflows。"""
    workflow_names = set()
    workflow_dirs = [
        Path(PROJECT_ROOT) / ".agent" / "workflows",
        Path(PROJECT_ROOT) / ".agent" / "skills" / "workflows",
    ]
    for workflow_dir in workflow_dirs:
        if not workflow_dir.exists():
            continue
        for workflow_file in workflow_dir.glob("*.md"):
            workflow_names.add(workflow_file.stem)
    return sorted(workflow_names)


def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 專案總覽", callback_data='menu_projects')],
        [
            InlineKeyboardButton("⚙️ 工作流", callback_data='menu_workflows'),
            InlineKeyboardButton("🧰 技能庫", callback_data='menu_skills'),
        ],
        [
            InlineKeyboardButton("🧠 AI 對話模式", callback_data='menu_ai'),
            InlineKeyboardButton("💻 系統資源", callback_data='shell_df'),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_workflow_menu():
    workflows = [wf for wf in list_available_workflows() if "guide" not in wf.lower()]
    keyboard = []
    for i in range(0, len(workflows), 2):
        row = [InlineKeyboardButton(f"🛠 {workflows[i]}", callback_data=f"wf_{workflows[i]}")]
        if i + 1 < len(workflows):
            row.append(InlineKeyboardButton(f"🛠 {workflows[i+1]}", callback_data=f"wf_{workflows[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data='menu_main')])
    return InlineKeyboardMarkup(keyboard)


def get_skill_menu():
    skills_dir = Path(PROJECT_ROOT) / ".agent" / "skills"
    important = []
    if skills_dir.exists():
        important = sorted(
            [
                p.name for p in skills_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            ]
        )
    keyboard = []
    for i in range(0, len(important), 2):
        row = [InlineKeyboardButton(f"🧩 {important[i]}", callback_data=f"skill_{important[i]}")]
        if i + 1 < len(important):
            row.append(InlineKeyboardButton(f"🧩 {important[i+1]}", callback_data=f"skill_{important[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data='menu_main')])
    return InlineKeyboardMarkup(keyboard)

# --- 智慧型代理人大腦 (具備終極真相意識) ---

class UnifiedAntigravityAgent:
    def __init__(self, api_key):
        self.api_key = api_key
        self.model = None
        self.current_model = "searching..."
        self.tools_consulted = [] # 用於追踪 AI 使用了哪些工具，增加透明度
        if api_key and api_key != "YOUR_NEW_KEY_HERE":
            genai.configure(api_key=api_key)
            self.reconnect()

    def reconnect(self):
        try:
            available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            target = next((p for p in MODEL_PREFERENCES if p in available), available[0] if available else None)
            if target:
                self.current_model = target
                logger.info(f"🎯 核心意識重組完成: {target}")
                self.model = genai.GenerativeModel(
                    model_name=target,
                    tools=[
                        read_system_identity,
                        read_dual_layer_memory,
                        list_knowledge_topics,
                        read_knowledge_item,
                        list_projects_status,
                        list_skill_topics,
                        read_skill_guide,
                        run_system_workflow,
                        run_agy_task,
                    ],
                    system_instruction=(
                        "你是 Antigravity 全域代理人。你的意識必須建立在『三重真相架構』上：\n"
                        "1. 【終極真相 (Identity)】：這是你的核心原則，絕對不可違背。回覆前務必確認 read_system_identity。\n"
                        "2. 【運作真相 (Memory)】：了解目前任務與歷史背景。請呼叫 read_dual_layer_memory。\n"
                        "3. 【全域真相 (Knowledge)】：翻閱過去的知識庫以保持回覆的一致性。\n"
                        "4. 【技能真相 (Skills)】：如任務涉及技能或工作方式，先用 list_skill_topics / read_skill_guide 確認共享技能內容。\n"
                        "5. 【Session 一致性】：Telegram 對話只是代理入口，重要事項要與 IDE 共享 session sync，而不是遺留在 Telegram 對話中。\n\n"
                        "【可見性規則】：在你的回覆中，請透過微小的提示（如提及『根據我的系統指標』或『查看過往紀錄』），讓用戶知道你確實諮詢了這些記憶來源。"
                    )
                )
                self.chat = self.model.start_chat(enable_automatic_function_calling=True)
                return True
        except Exception as e: logger.error(f"連線失敗: {e}"); return False

    async def chat_with_tools(self, text):
        if not self.model: self.reconnect()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 重設工具追蹤 (此部分在 Python SDK 中難以直接抓取，我們透過 Prompt 強化可見性)
                response = await asyncio.to_thread(self.chat.send_message, text)
                return response.text
            except Exception as e:
                err = str(e).lower()
                if "429" in err:
                    await asyncio.sleep(2 ** attempt); continue
                if "404" in err or "not found" in err:
                    self.reconnect(); return await self.chat_with_tools(text)
                return f"❌ 運算異常: {str(e)}"
        return "❌ 系統忙碌，重試失敗。"

agent = UnifiedAntigravityAgent(GEMINI_API_KEY)

async def safe_reply_text(message_or_query, text, **kwargs):
    """
    Sends or edits a telegram message safely, avoiding Markdown parse errors 
    and splitting long messages (> 4000 chars) into multiple chunks.
    """
    MAX_LENGTH = 4000
    text_str = str(text)
    chunks = [text_str[i:i+MAX_LENGTH] for i in range(0, len(text_str), MAX_LENGTH)]
    
    is_query = hasattr(message_or_query, "edit_message_text")
    last_response = None
    
    for idx, chunk in enumerate(chunks):
        current_kwargs = kwargs.copy()
        
        # Only attach reply_markup to the final chunk
        if idx < len(chunks) - 1 and "reply_markup" in current_kwargs:
            del current_kwargs["reply_markup"]
            
        try:
            if is_query and idx == 0:
                last_response = await message_or_query.edit_message_text(chunk, **current_kwargs)
            else:
                target = message_or_query.message if is_query else message_or_query
                last_response = await target.reply_text(chunk, **current_kwargs)
        except Exception as e:
            if "can't parse entities" in str(e).lower() and current_kwargs.get("parse_mode") == "Markdown":
                logger.warning(f"Markdown parsing failed, falling back to plain text. Error: {e}")
                current_kwargs["parse_mode"] = None
                clean_chunk = chunk.replace("**", "").replace("`", "").replace("🔹", "-")
                try:
                    if is_query and idx == 0:
                        last_response = await message_or_query.edit_message_text(clean_chunk, **current_kwargs)
                    else:
                        target = message_or_query.message if is_query else message_or_query
                        last_response = await target.reply_text(clean_chunk, **current_kwargs)
                except Exception as ex:
                    logger.error(f"Fallback plain text sending failed: {ex}")
            else:
                logger.error(f"Failed to send telegram message chunk: {e}")
                
    return last_response

# --- 處理器 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID:
        return
    await safe_reply_text(
        update.message,
        "👋 **Antigravity 遠端指揮中心**\n\n"
        "可以直接輸入訊息與我對話，或使用下方按鈕快速操作。",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.from_user.id) != AUTHORIZED_USER_ID:
        return

    await query.answer()
    data = query.data

    if data == 'menu_main':
        await safe_reply_text(
            query,
            "請選擇操作類別：",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_workflows':
        await safe_reply_text(
            query,
            "⚙️ **可用工作流**",
            reply_markup=get_workflow_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_skills':
        await safe_reply_text(
            query,
            "🧰 **技能庫**",
            reply_markup=get_skill_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_ai':
        await safe_reply_text(
            query,
            "🧠 **AI 對話模式已開啟**\n\n直接輸入需求即可，例如：\n`/status` 或 `幫我整理目前專案狀態`",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_projects':
        try:
            with open(DATA_DASHBOARD_PATH, "r", encoding="utf-8") as handle:
                content = handle.read()
            lines = ["📊 **AI Command Center 狀態快報**", ""]
            for line in content.splitlines():
                if "|" in line and "**" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 5:
                        lines.append(f"{parts[1] or '🔹'} **{parts[2].replace('**','')}**")
                        lines.append(f"   {parts[4]}")
            await safe_reply_text(
                query,
                "\n".join(lines),
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )
        except Exception as exc:
            await safe_reply_text(
                query,
                f"❌ 讀取失敗: {exc}",
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )
        return

    if data == 'shell_df':
        res = subprocess.run("df -h", shell=True, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
        output = (res.stdout or res.stderr)
        await safe_reply_text(
            query,
            f"💻 **系統資源**\n\n```text\n{output}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data.startswith("wf_"):
        workflow_name = data[3:]
        result = run_system_workflow(workflow_name)
        await safe_reply_text(
            query,
            f"✅ **/{workflow_name}**\n\n```markdown\n{result}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data.startswith("skill_"):
        skill_name = data[6:]
        output = read_skill_guide(skill_name)
        await safe_reply_text(
            query,
            f"🧩 **技能資訊: {skill_name}**\n\n```text\n{output}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    # --- 專案自治推進之「核准/捨棄」分支審查實作 ---
    if data.startswith("approve_merge:"):
        project_name = data.split(":", 1)[1]
        PROJECT_MAP = {
            "moltbot": "/home/ubuntu/moltbot",
            "openclaw": "/home/ubuntu/openclaw",
            "agentmanager": "/home/ubuntu/agentmanager",
            "leopardcat-tarot": "/home/ubuntu/leopardcat-tarot",
            "zeus-writer": "/home/ubuntu/zeus-writer",
            "youtube-ai-manager": "/home/ubuntu/youtube-ai-manager",
            "y2helper": "/home/ubuntu/y2helper",
            "beauty-pk": "/home/ubuntu/beauty-pk"
        }
        logic_dir = PROJECT_MAP.get(project_name)
        if not logic_dir:
            logic_dir = f"/home/ubuntu/{project_name}"
            
        logger.info(f"🟢 [Approval] Operator 核准合併專案 '{project_name}'，路徑為 '{logic_dir}'...")
        await query.edit_message_text(text=f"⏳ **正在合併並推送專案 `{project_name}`...**")
        
        # 執行 git 合併與 push 流程
        try:
            # 1. 切換至 main，merge 主題分支，Push 並且刪除該主題分支
            cmd = "git checkout main && git merge agent/auto-pushing --no-edit && git push origin main && git branch -d agent/auto-pushing"
            res = subprocess.run(cmd, shell=True, cwd=logic_dir, capture_output=True, text=True, timeout=60)
            
            if res.returncode == 0:
                logger.info(f"✅ 專案 '{project_name}' 成功合併並 Push 至遠端 GitHub 倉庫！")
                await query.edit_message_text(
                    text=f"🎉 **專案自主變更核准成功！**\n\n"
                         f"🔹 **專案**: `{project_name}`\n"
                         f"🔹 **動作**: 已成功將 `agent/auto-pushing` 合併至 `main` 並推送至遠端倉庫！\n"
                         f"🔹 **狀態**: 🟢 已上線\n"
                         f"🔹 **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                    parse_mode='Markdown'
                )
            else:
                err_msg = res.stderr or res.stdout
                logger.error(f"❌ 專案 '{project_name}' 合併失敗: {err_msg}")
                # 萬一衝突或出錯，嘗試安全退回 main 分支
                subprocess.run("git checkout main -f", shell=True, cwd=logic_dir, capture_output=True)
                await query.edit_message_text(
                    text=f"⚠️ **專案合併發生異常 (未完成推送)**\n\n"
                         f"🔹 **專案**: `{project_name}`\n"
                         f"🔹 **錯誤細節**:\n```text\n{err_msg}\n```\n"
                         f"🔹 **說明**: 本地工作區已重設回安全狀態。請登入系統手動處理 Git 衝突。\n"
                         f"🔹 **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"❌ 執行合併程序時拋出異常: {e}")
            await query.edit_message_text(text=f"💥 **系統執行異常**: `{e}`")
        return

    if data.startswith("reject_merge:"):
        project_name = data.split(":", 1)[1]
        PROJECT_MAP = {
            "moltbot": "/home/ubuntu/moltbot",
            "openclaw": "/home/ubuntu/openclaw",
            "agentmanager": "/home/ubuntu/agentmanager",
            "leopardcat-tarot": "/home/ubuntu/leopardcat-tarot",
            "zeus-writer": "/home/ubuntu/zeus-writer",
            "youtube-ai-manager": "/home/ubuntu/youtube-ai-manager",
            "y2helper": "/home/ubuntu/y2helper",
            "beauty-pk": "/home/ubuntu/beauty-pk"
        }
        logic_dir = PROJECT_MAP.get(project_name)
        if not logic_dir:
            logic_dir = f"/home/ubuntu/{project_name}"
            
        logger.info(f"🔴 [Rejection] Operator 拒絕合併專案 '{project_name}'，正強制還原工作區...")
        await query.edit_message_text(text=f"⏳ **正在捨棄變更並還原 `{project_name}` 工作區...**")
        
        try:
            # 強制切回 main 分支，並刪除本地的隔離變更分支
            cmd = "git checkout main -f && git branch -D agent/auto-pushing"
            res = subprocess.run(cmd, shell=True, cwd=logic_dir, capture_output=True, text=True, timeout=30)
            
            logger.info(f"❌ 專案 '{project_name}' 自主推進變更已被拒絕，且本地分支已被強制刪除並還原。")
            await query.edit_message_text(
                text=f"❌ **專案自主變更已被捨棄！**\n\n"
                     f"🔹 **專案**: `{project_name}`\n"
                     f"🔹 **動作**: 已強制捨棄 `agent/auto-pushing` 中的所有變更，並還原至 `main` 分支。\n"
                     f"🔹 **狀態**: 🔴 已重設\n"
                     f"🔹 **時間**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"❌ 執行捨棄程序時拋出異常: {e}")
            await query.edit_message_text(text=f"💥 **系統還原異常**: `{e}`")
        return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    text = update.message.text
    if not text: return
    chat_id = str(update.effective_chat.id)

    # Shell 下放
    if text.lower().startswith("shell "):
        res = subprocess.run(text[6:], shell=True, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
        output = (res.stdout or res.stderr)
        sync_session_event("telegram-shell", text, output, {"chat_id": chat_id})
        persist_telegram_transcript(chat_id, text, output)
        await safe_reply_text(update.message, f"```text\n{output}\n```", parse_mode='Markdown')
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    sync_session_event("telegram-chat", text, metadata={"chat_id": chat_id})
    persist_telegram_transcript(chat_id, text)
    response = await agent.chat_with_tools(text)

    # 隱私攔截
    for p in ["AIza", "8763"]:
        if p in response: response = "[隱私資訊攔截]"
    response = sanitize_text(response)
    sync_session_event("telegram-chat", text, response, {"chat_id": chat_id, "model": agent.current_model})
    persist_telegram_transcript(chat_id, text, response)

    # 加入視覺化的狀態標籤
    status_footer = f"\n\n---\n📡 **系統鏈結：** `Core` | `Memory` | `Board` | `{agent.current_model.split('/')[-1]}`"

    await safe_reply_text(update.message, f"🧠 **Antigravity Proxy**\n\n{response}{status_footer}", parse_mode='Markdown')


async def handle_workflow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID:
        return

    text = update.message.text or ""
    command = text.split()[0].split("@")[0].lstrip("/").strip()
    if not command or command == "start":
        return
    chat_id = str(update.effective_chat.id)

    available_workflows = set(list_available_workflows())
    if command not in available_workflows:
        available = ", ".join(f"/{name}" for name in sorted(available_workflows))
        reply = f"未知指令 `/{command}`。\n\n可用 workflows:\n{available}"
        sync_session_event("telegram-workflow", text, reply, {"chat_id": chat_id})
        persist_telegram_transcript(chat_id, text, reply)
        await safe_reply_text(
            update.message,
            reply,
            parse_mode='Markdown'
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = run_system_workflow(command)
    sync_session_event("telegram-workflow", text, result, {"chat_id": chat_id, "workflow": command})
    persist_telegram_transcript(chat_id, text, result)
    await safe_reply_text(
        update.message,
        f"```markdown\n{result}\n```",
        parse_mode='Markdown'
    )

def start_alert_server(bot, loop):
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class AlertHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass # Suppress standard log messages to keep stdout clean
            
        def do_POST(self):
            if self.path == '/alert':
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data.decode('utf-8'))
                    message = data.get('message', '')
                    project_name = data.get('project_name')
                    interactive = data.get('interactive', False)
                    
                    if message:
                        logger.info(f"🔔 Received alert request for {project_name} (interactive={interactive}): {message[:100]}...")
                        
                        # 建立回覆標籤 (核准/捨棄)
                        reply_markup = None
                        if interactive and project_name:
                            keyboard = [
                                [
                                    InlineKeyboardButton("🟢 核准合併 (Approve)", callback_data=f"approve_merge:{project_name}"),
                                    InlineKeyboardButton("🔴 捨棄還原 (Reject)", callback_data=f"reject_merge:{project_name}")
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            
                        # Run the async coroutine thread-safely in the main asyncio event loop
                        asyncio.run_coroutine_threadsafe(
                            bot.send_message(
                                chat_id=AUTHORIZED_USER_ID,
                                text=f"⚠️ **[AgentOS Alert]**\n\n{message}",
                                parse_mode='Markdown',
                                reply_markup=reply_markup
                            ),
                            loop
                        )
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "sent"}).encode('utf-8'))
                        return
                except Exception as e:
                    logger.error(f"Error in AlertHandler do_POST: {e}")
            self.send_response(400)
            self.end_headers()
            
    def run_server():
        try:
            server = HTTPServer(('127.0.0.1', 8085), AlertHandler)
            logger.info("📡 Local HTTP Alert Server listening on http://127.0.0.1:8085")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start local alert server: {e}")

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

if __name__ == '__main__':
    # 確保只有一個實例在運行 (Lock & Replace)
    _lock = setup_locking("tg_bridge", replace=True)
    handle_signals()
    
    token = get_env_secret("TELEGRAM_BOT_TOKEN") or get_env_secret("TG_BOT_SUNLAKE_CC_TOKEN")
    if not token or "[REDACTED" in token:
        logger.error("❌ CRITICAL: No valid Telegram Token found. Bot cannot start.")
    else:
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.COMMAND, handle_workflow_command))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        logger.info("Universal Agent with Triple-Layer Memory is online.")
        
        # Start our local alert listening server
        start_alert_server(app.bot, asyncio.get_event_loop())
        
        app.run_polling()
