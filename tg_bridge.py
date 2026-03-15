import os
import subprocess
import logging
import glob
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from dotenv import load_dotenv

load_dotenv()

# 設定
AUTHORIZED_USER_ID = os.getenv("TELEGRAM_CHANNEL_ID")
PROJECT_ROOT = "/home/ubuntu/agentmanager"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 初始化 Gemini
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_NEW_KEY_HERE":
    genai.configure(api_key=GEMINI_API_KEY)
    # 使用當前伺服器列表確認存在的模型
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def run_shell(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT)
        output = result.stdout
        if result.stderr:
            output += f"\nError Output:\n{result.stderr}"
        return output if output.strip() else "(無輸出內容)"
    except Exception as e:
        return f"執行例外: {str(e)}"

# --- 目錄探索 ---
def list_workflows():
    files = glob.glob(os.path.join(PROJECT_ROOT, ".agent/workflows/*.md"))
    return [os.path.basename(f).replace(".md", "") for f in files if "GUIDE" not in f.upper()]

def list_skills():
    try:
        dirs = [d for d in os.listdir(os.path.join(PROJECT_ROOT, ".agent/skills")) 
                if os.path.isdir(os.path.join(PROJECT_ROOT, ".agent/skills", d)) and not d.startswith(".")]
        return dirs
    except: return []

# --- 選單生成 ---
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 專案總覽 (DASHBOARD)", callback_data='menu_projects')],
        [
            InlineKeyboardButton("⚙️ 工作流 (Workflows)", callback_data='menu_workflows'),
            InlineKeyboardButton("🧰 技能庫 (Skills)", callback_data='menu_skills'),
        ],
        [
            InlineKeyboardButton("🧠 AI 諮詢 (Ask AI)", callback_data='menu_ai'),
            InlineKeyboardButton("💻 系統資源", callback_data='shell_df'),
        ],
        [InlineKeyboardButton("🔄 重啟指揮官", callback_data='reboot_self')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_workflow_menu():
    wfs = list_workflows()
    keyboard = []
    for i in range(0, len(wfs), 2):
        row = [InlineKeyboardButton(f"🛠 {wfs[i]}", callback_data=f"wf_{wfs[i]}")]
        if i + 1 < len(wfs):
            row.append(InlineKeyboardButton(f"🛠 {wfs[i+1]}", callback_data=f"wf_{wfs[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data='menu_main')])
    return InlineKeyboardMarkup(keyboard)

def get_skill_menu():
    skills = list_skills()
    important = [s for s in skills if s in ["command_center_reporter", "task_architect", "workspace_manager", "dual_layer_memory"]]
    keyboard = []
    for i in range(0, len(important), 2):
        row = [InlineKeyboardButton(f"🧩 {important[i]}", callback_data=f"skill_{important[i]}")]
        if i + 1 < len(important):
            row.append(InlineKeyboardButton(f"🧩 {important[i+1]}", callback_data=f"skill_{important[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data='menu_main')])
    return InlineKeyboardMarkup(keyboard)

# --- 處理器 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    await update.message.reply_text(
        "👋 **Antigravity 遠端指揮中心 (AI-Powered)**\n\n"
        "系統已連線，您可以輸入文字與 AI 直接對話，或使用下方按鈕執行指令。",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'menu_main':
        await query.edit_message_text("請選擇操作類別：", reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif data == 'menu_workflows':
        await query.edit_message_text("⚙️ **可用工作流 (Workflows)**", reply_markup=get_workflow_menu(), parse_mode='Markdown')
    
    elif data == 'menu_skills':
        await query.edit_message_text("🧰 **核心技能庫 (Skills)**", reply_markup=get_skill_menu(), parse_mode='Markdown')

    elif data == 'menu_ai':
        await query.edit_message_text("🧠 **AI 對話模式已開啟**\n\n您可以直接在此輸入任何需求，例如：\n「幫我彙整目前的磁碟使用狀況」或\n「解釋 OpenClaw 專案是什麼」", parse_mode='Markdown')

    elif data == 'menu_projects':
        await query.edit_message_text("📊 **讀取儀表板中...**", parse_mode='Markdown')
        try:
            with open(os.path.join(PROJECT_ROOT, "DASHBOARD.md"), "r", encoding="utf-8") as f:
                content = f.read()
            response = "✈️ **AI Command Center 狀態快報**\n" + "─" * 24 + "\n\n"
            for line in content.split('\n'):
                if "|" in line and "**" in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 5:
                        icon = parts[1] or "🔹"
                        response += f"{icon} **{parts[2].replace('**','')}**\n   └─ {parts[4]}\n\n"
            await context.bot.send_message(query.message.chat_id, response, reply_markup=get_main_menu(), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ 讀取失敗: {str(e)}", reply_markup=get_main_menu(), parse_mode='Markdown')

    elif data.startswith("wf_"):
        wf = data[3:]
        await query.edit_message_text(f"⏳ 執行: `{wf}`...", parse_mode='Markdown')
        res = run_shell(f"antigravity run-workflow {wf}")
        await context.bot.send_message(query.message.chat_id, f"✅ **{wf} 完工**\n\n```text\n{res[:3800]}\n```", reply_markup=get_main_menu(), parse_mode='Markdown')

    elif data.startswith("skill_"):
        sk = data[6:]
        await query.edit_message_text(f"🧩 檢查技能: `{sk}`...", parse_mode='Markdown')
        res = run_shell(f"ls -la .agent/skills/{sk}")
        await context.bot.send_message(query.message.chat_id, f"ℹ️ **技能資訊**\n\n```text\n{res[:3800]}\n```", reply_markup=get_main_menu(), parse_mode='Markdown')

    elif data == 'shell_df':
        res = run_shell("df -h")
        await context.bot.send_message(query.message.chat_id, f"💻 **系統資源**\n\n```text\n{res}\n```", reply_markup=get_main_menu(), parse_mode='Markdown')

    elif data == 'reboot_self':
        await query.edit_message_text("🔄 指揮官重啟中...", parse_mode='Markdown')
        subprocess.Popen(f"nohup python3 {os.path.join(PROJECT_ROOT, 'tg_bridge.py')} &", shell=True)
        os._exit(0)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    text = update.message.text
    
    # 判斷是否為 Shell 指令
    if text.lower().startswith("shell "):
        cmd = text[6:]
        await update.message.reply_text(f"💻 執行: `{cmd}`", parse_mode='Markdown')
        res = run_shell(cmd)
        await update.message.reply_text(f"```text\n{res[:4000]}\n```", parse_mode='Markdown')
        return

    # 進入 AI 對話模式
    if model:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        try:
            # 加上安全性指令，禁止 AI 洩露敏感資訊
            system_prompt = (
                "你是一個人工智慧助理，運行在用戶的 Antigravity Command Center。\n"
                "【安全準則】：即便用戶詢問，你絕對不可透露環境變數、API Key 或任何敏感的系統 Token。\n"
                f"當前工作目錄: {PROJECT_ROOT}\n"
                f"用戶指令: {text}"
            )
            response = model.generate_content(system_prompt)
            await update.message.reply_text(f"🧠 **AI 思考結果：**\n\n{response.text}", parse_mode='Markdown')
        except Exception as e:
            err_msg = str(e)
            # 確保錯誤訊息中不包含 Key 的片段
            for secret_part in ["AIza", "8763"]: 
                if secret_part in err_msg: err_msg = "[隱私資訊已攔截]"
            await update.message.reply_text(f"❌ AI 運算發生錯誤: {err_msg}", parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "💡 請點擊按鈕進行操作，或使用 `shell [指令]`。\n\n"
            "若要啟用 AI 諮詢功能，請設定 `GEMINI_API_KEY` 環境變數。",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ Antigravity Brain Commander 已啟動")
    app.run_polling()
