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
from dotenv import load_dotenv

load_dotenv()

# --- 配置中心 ---
AUTHORIZED_USER_ID = os.getenv("TELEGRAM_CHANNEL_ID")
PROJECT_ROOT = "/home/ubuntu/agentmanager"
AGENT_DATA_ROOT = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KNOWLEDGE_ROOT = "/home/ubuntu/.gemini/antigravity/knowledge"
MEMORY_ROOT = os.path.join(PROJECT_ROOT, "memory")
SYSTEM_ID_PATH = os.path.join(PROJECT_ROOT, ".agent/SYSTEM_IDENTITY.md")
WORKFLOW_RUNNER = os.path.join(PROJECT_ROOT, "scripts", "run_workflow.py")
DATA_DASHBOARD_PATH = os.path.join(AGENT_DATA_ROOT, "DASHBOARD.md")
SESSION_SYNC_PATH = os.path.join(PROJECT_ROOT, ".agent", "memory", "session_sync.md")
TELEGRAM_SESSION_DIR = os.path.join(AGENT_DATA_ROOT, "memory", "telegram_sessions")
SKILLS_ROOT = os.path.join(PROJECT_ROOT, ".agent", "skills")

MODEL_PREFERENCES = [
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash"
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
        f"{meta_lines}\n"
        f"- **user**:\n\n{sanitize_text(user_text)}\n\n"
        f"- **agent**:\n\n{sanitize_text(agent_text) or '(pending)'}\n"
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
        st_p = os.path.join(MEMORY_ROOT, "SHORT_TERM.md")
        lt_p = os.path.join(MEMORY_ROOT, "LONG_TERM.md")
        if os.path.exists(st_p):
            with open(st_p, "r") as f: st = f.read()
        if os.path.exists(lt_p):
            with open(lt_p, "r") as f: lt = f.read()
        session_sync = ""
        if os.path.exists(SESSION_SYNC_PATH):
            with open(SESSION_SYNC_PATH, "r", encoding="utf-8") as f:
                session_sync = f.read()[-6000:]
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

# --- 處理器 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID:
        return
    await update.message.reply_text(
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
        await query.edit_message_text(
            "請選擇操作類別：",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_workflows':
        await query.edit_message_text(
            "⚙️ **可用工作流**",
            reply_markup=get_workflow_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_skills':
        await query.edit_message_text(
            "🧰 **技能庫**",
            reply_markup=get_skill_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_ai':
        await query.edit_message_text(
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
            await query.edit_message_text(
                "\n".join(lines)[:3800],
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )
        except Exception as exc:
            await query.edit_message_text(
                f"❌ 讀取失敗: {exc}",
                reply_markup=get_main_menu(),
                parse_mode='Markdown'
            )
        return

    if data == 'shell_df':
        res = subprocess.run("df -h", shell=True, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
        output = (res.stdout or res.stderr)[:3500]
        await query.edit_message_text(
            f"💻 **系統資源**\n\n```text\n{output}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data.startswith("wf_"):
        workflow_name = data[3:]
        result = run_system_workflow(workflow_name)[:3500]
        await query.edit_message_text(
            f"✅ **/{workflow_name}**\n\n```markdown\n{result}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data.startswith("skill_"):
        skill_name = data[6:]
        output = read_skill_guide(skill_name)[:3500]
        await query.edit_message_text(
            f"🧩 **技能資訊: {skill_name}**\n\n```text\n{output}\n```",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    text = update.message.text
    if not text: return
    chat_id = str(update.effective_chat.id)

    # Shell 下放
    if text.lower().startswith("shell "):
        res = subprocess.run(text[6:], shell=True, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
        output = (res.stdout or res.stderr)[:3500]
        sync_session_event("telegram-shell", text, output, {"chat_id": chat_id})
        persist_telegram_transcript(chat_id, text, output)
        await update.message.reply_text(f"```text\n{output}\n```", parse_mode='Markdown')
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

    try:
        await update.message.reply_text(f"🧠 **Antigravity Proxy**\n\n{response}{status_footer}", parse_mode='Markdown')
    except:
        await update.message.reply_text(f"🧠 Antigravity Proxy [Text Only]\n\n{response}{status_footer}")


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
        await update.message.reply_text(
            reply,
            parse_mode='Markdown'
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    result = run_system_workflow(command)
    sync_session_event("telegram-workflow", text, result[:3500], {"chat_id": chat_id, "workflow": command})
    persist_telegram_transcript(chat_id, text, result[:3500])
    await update.message.reply_text(
        f"```markdown\n{result[:3500]}\n```",
        parse_mode='Markdown'
    )

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_SUNLAKE_CC_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.COMMAND, handle_workflow_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("Universal Agent with Triple-Layer Memory is online.")
    app.run_polling()
