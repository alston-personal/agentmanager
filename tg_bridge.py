import os
import subprocess
import logging
import glob
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from dotenv import load_dotenv

load_dotenv()

# 設定
AUTHORIZED_USER_ID = os.getenv("TELEGRAM_CHANNEL_ID")
PROJECT_ROOT = "/home/ubuntu/agentmanager"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def run_shell(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT)
        output = result.stdout
        if result.stderr:
            output += f"\nError:\n{result.stderr}"
        return output if output.strip() else "(無輸出內容)"
    except Exception as e:
        return f"執行發生例外: {str(e)}"

# --- 目錄探索 ---
def list_workflows():
    files = glob.glob(os.path.join(PROJECT_ROOT, ".agent/workflows/*.md"))
    # 過濾掉一些輔助性的 md 檔案
    return [os.path.basename(f).replace(".md", "") for f in files if "GUIDE" not in f.upper()]

def list_skills():
    try:
        dirs = [d for d in os.listdir(os.path.join(PROJECT_ROOT, ".agent/skills")) 
                if os.path.isdir(os.path.join(PROJECT_ROOT, ".agent/skills", d)) and not d.startswith(".")]
        return dirs
    except:
        return []

# --- 選單生成 ---
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📂 專案總覽 (DASHBOARD)", callback_data='menu_projects')],
        [
            InlineKeyboardButton("⚙️ 工作流 (Workflows)", callback_data='menu_workflows'),
            InlineKeyboardButton("🧰 技能庫 (Skills)", callback_data='menu_skills'),
        ],
        [
            InlineKeyboardButton("💻 系統資源 (df -h)", callback_data='shell_df'),
            InlineKeyboardButton("🔄 重啟服務", callback_data='reboot_self'),
        ]
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
    keyboard = []
    # 這裡只列出主要技能目錄
    important_skills = [s for s in skills if s in ["command_center_reporter", "task_architect", "workspace_manager", "dual_layer_memory"]]
    for i in range(0, len(important_skills), 2):
        row = [InlineKeyboardButton(f"🧩 {important_skills[i]}", callback_data=f"skill_{important_skills[i]}")]
        if i + 1 < len(important_skills):
            row.append(InlineKeyboardButton(f"🧩 {important_skills[i+1]}", callback_data=f"skill_{important_skills[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data='menu_main')])
    return InlineKeyboardMarkup(keyboard)

# --- 處理器 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    await update.message.reply_text(
        "👋 **歡迎來到 Antigravity 遠端指揮中心**\n\n"
        "這套系統已與您的 **AI Command Center** 深度整合。您可以即時監控所有 Agent 的進度，或從手機遠端調度工作流。\n\n"
        "請選擇操作類別：",
        reply_markup=get_main_menu(),
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'menu_main':
        await query.edit_message_text(
            "👋 **Antigravity 遠端指揮中心**\n\n請選擇操作類別：",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_workflows':
        await query.edit_message_text(
            "⚙️ **可用工作流 (Workflows)**\n\n這些是您在 `.agent/workflows` 中定義的自動化流程：",
            reply_markup=get_workflow_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_skills':
        await query.edit_message_text(
            "🧰 **整合技能庫 (Skills)**\n\n以下是目前 AI Center 裝備的核心技能：",
            reply_markup=get_skill_menu(),
            parse_mode='Markdown'
        )
        return

    if data == 'menu_projects':
        await query.edit_message_text("📊 **正在掃描儀表板...**")
        try:
            with open(os.path.join(PROJECT_ROOT, "DASHBOARD.md"), "r", encoding="utf-8") as f:
                content = f.read()
            
            response = "✈️ **AI Command Center 飛行甲板**\n" + "─" * 24 + "\n\n"
            
            # 專門解析表格
            found_projects = False
            lines = content.split('\n')
            for line in lines:
                if "|" in line and "**" in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 5:
                        icon = parts[1] if parts[1] else "🔹"
                        name = parts[2].replace("**", "")
                        status = parts[4].replace("🟢", "🟢 ").replace("🚧", "🚧 ").replace("✅", "✅ ")
                        response += f"{icon} **{name}**\n   └─ {status}\n\n"
                        found_projects = True
            
            if not found_projects:
                response = "⚠️ 儀表板目前沒有進行中的專案列。請檢查 `DASHBOARD.md`。"
                
        except Exception as e:
            response = f"❌ 儀表板連線失敗: {str(e)}"
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=response,
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )
        return

    # --- 執行行為 ---
    cmd_to_run = ""
    action_name = ""
    
    if data.startswith("wf_"):
        wf_name = data[3:]
        action_name = f"工作流: {wf_name}"
        await query.edit_message_text(f"⏳ **執行中:** `{wf_name}`...", parse_mode='Markdown')
        cmd_to_run = f"antigravity run-workflow {wf_name}"
    
    elif data.startswith("skill_"):
        skill_name = data[6:]
        action_name = f"技能檢查: {skill_name}"
        await query.edit_message_text(f"🔍 **檢索技能資訊:** `{skill_name}`...", parse_mode='Markdown')
        cmd_to_run = f"ls -la {os.path.join(PROJECT_ROOT, '.agent/skills', skill_name)}"
    
    elif data == 'shell_df':
        action_name = "系統資源狀態"
        cmd_to_run = "df -h"
        
    elif data == 'reboot_self':
        await query.edit_message_text("🔄 **Bot 指揮官重啟中...**", parse_mode='Markdown')
        subprocess.Popen(f"nohup python3 {os.path.join(PROJECT_ROOT, 'tg_bridge.py')} &", shell=True)
        os._exit(0)

    if cmd_to_run:
        res = run_shell(cmd_to_run)
        if len(res) > 3800: res = res[:3800] + "\n... (過長截斷)"
        
        # 美化輸出排版
        formatted_res = f"✅ **{action_name} 執行完成**\n" + "─" * 24 + f"\n\n```text\n{res}\n```"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=formatted_res,
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != AUTHORIZED_USER_ID: return
    text = update.message.text
    if text.lower().startswith("shell "):
        cmd = text[6:]
        await update.message.reply_text(f"💻 **手動執行指令**\n`{cmd}`", parse_mode='Markdown')
        res = run_shell(cmd)
        await update.message.reply_text(f"```text\n{res[:4000]}\n```", parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "💡 **提示**\n請點擊下方的圖形化按鈕進行操作。\n您可以輸入 `shell [指令]` 執行任意指令。",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
        )

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: exit(1)
    
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    print("✅ Antigravity Premium Command Center 已就緒")
    app.run_polling()
