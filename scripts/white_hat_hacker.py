#!/usr/bin/env python3
"""
🛡️ AgentOS Resident White-Hat Hacker Automation
================================================
每日自動掃描主機安全性（包含敏感權限、暴露端口、明文金鑰等），
呼叫 Gemini 進行漏洞分析並產出安全性審計報告，
自動產生安全修復 TODO 任務並注入中央 TASK_BOARD，由 Lobster 自動執行修復！
"""
import os
import re
import sys
import json
import socket
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (🛡️ WhiteHat) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/ubuntu/agent-data/logs/white_hat.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("WhiteHat")

HOME = Path("/home/ubuntu")
AGENT_DATA_ROOT = HOME / "agent-data"
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
STATUS_MD = PROJECTS_DIR / "security-audit" / "STATUS.md"
REPORT_MD = AGENT_DATA_ROOT / "WHITE_HAT_REPORT.md"

# 載入全域環境變數
def load_env():
    env_path = HOME / "agentmanager" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

load_env()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

def send_telegram_alert(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception:
        pass

# ── 1. 實體安全性掃描 ───────────────────────────────────────────────────────

def scan_file_permissions() -> list[dict]:
    """掃描所有專案中的敏感檔案權限是否過於寬鬆 (大於 600)"""
    vulnerabilities = []
    env_files = list(HOME.glob("*/.env")) + list(HOME.glob("*/projects/*/.env"))
    
    # 加上全域 .env
    global_env = HOME / "agentmanager" / ".env"
    if global_env.exists() and global_env not in env_files:
        env_files.append(global_env)
        
    for path in env_files:
        if path.is_symlink() or not path.exists():
            continue
        stat = path.stat()
        mode = stat.st_mode & 0o777
        # 如果權限大於 600 (即群組或其他人可讀寫)
        if mode & 0o077 > 0:
            vulnerabilities.append({
                "type": "unsecure_file_permission",
                "path": str(path).replace("/home/ubuntu", "~"),
                "permission": oct(mode),
                "severity": "MEDIUM",
                "description": f"金鑰設定檔權限為 {oct(mode)}，非擁有者亦可讀取。應修正為 600 (-rw-------)。"
            })
    return vulnerabilities

def scan_open_ports() -> list[dict]:
    """掃描當前綁定於 0.0.0.0 或 * 的對外暴露端口"""
    vulnerabilities = []
    try:
        res = subprocess.run("ss -ltnp", shell=True, capture_output=True, text=True, timeout=10)
        lines = res.stdout.strip().splitlines()
        for line in lines:
            if "LISTEN" not in line:
                continue
            parts = line.split()
            if len(parts) >= 5:
                local_addr = parts[3]
                process_info = parts[5] if len(parts) >= 6 else "Unknown"
                
                # 判定是否暴露給外部所有 IP (0.0.0.0 或 *)
                if local_addr.startswith("0.0.0.0:") or local_addr.startswith("*:") or local_addr.startswith("[::]:"):
                    port = local_addr.split(":")[-1]
                    # 排除常見合規公共服務 (如 80, 443)，但警告管理端口如 3001, 8080, 8088
                    if port in ["80", "443"]:
                        continue
                        
                    severity = "LOW"
                    if port in ["3001", "8088", "18789", "5678", "8080"]:
                        severity = "MEDIUM"
                        
                    vulnerabilities.append({
                        "type": "exposed_port",
                        "port": port,
                        "address": local_addr,
                        "process": process_info,
                        "severity": severity,
                        "description": f"連接埠 {port} ({process_info}) 綁定於 {local_addr}，可直接由外部網路存取。若未設定防火牆，可能造成越權存取。"
                    })
    except Exception as e:
        logger.error(f"掃描開放連接埠失敗: {e}")
    return vulnerabilities

def scan_exposed_secrets() -> list[dict]:
    """簡易掃描是否有殘留的明文備份檔或敏感字串暴露"""
    vulnerabilities = []
    # 檢查是否有備份檔殘留
    for path in HOME.glob("*/*.bak"):
        if "node_modules" in str(path):
            continue
        vulnerabilities.append({
            "type": "backup_secret_leak",
            "path": str(path).replace("/home/ubuntu", "~"),
            "severity": "LOW",
            "description": f"發現殘留的備份檔案 {path.name}，可能洩漏敏感金鑰歷史紀錄。應定期清理。"
        })
    return vulnerabilities

# ── 2. 呼叫 Gemini 產出安全報告 ──────────────────────────────────────────────

def run_security_analysis(facts: dict) -> tuple[str, list[str]]:
    """呼叫 Gemini 進行資安風險分析，並在 API 額度超限時自動切換至備用金鑰與本地規則引擎"""
    # 取得所有可能的金鑰進行輪替
    keys_to_try = [
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_1"),
        os.environ.get("CONTINUE_GEMINI_API_KEY")
    ]
    # 過濾掉空值
    keys_to_try = [k for k in keys_to_try if k]
    
    report_content = ""
    todos = []
    success = False
    
    # 嘗試使用 Gemini API
    for idx, key in enumerate(keys_to_try):
        if not key:
            continue
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            prompt = f"""
你是一位頂尖的白帽駭客與 DevSecOps 資安專家，擔任我們自律生態系統 **AgentOS** 的「常駐安全顧問」。
請針對以下從實體 VM 主機中掃描出來的真實安全威脅事實，進行精準的風險評估，並給予繁體中文（台灣）的安全審計報告。

【系統安全性檢測事實數據】：
{json.dumps(facts, indent=2, ensure_ascii=False)}

【您的任務】：
1. 撰寫一份專業的 **每日安全性審計報告 (Daily Security Audit Report)**。
2. 針對所有掃描出的威脅，給出清晰的漏洞危害說明。
3. **最重要**：將這些修復建議轉化為「Lobster 自律執行引擎」可以直接在終端機運行的「具體、明確、可執行的待辦事項（TODO List）」。
   - 每一項 TODO 必須以 `- [ ] [Security] 任務敘述` 的標準格式寫在報告末尾。
   - 任務敘述必須非常具體，例如：「[Security] 將 ~/zeus-writer/.env 檔案權限修正為 600 (-rw-------)」或「[Security] 清除 ~/agentmanager/ 殘留的 *.bak 備份檔案」。
   - 這些任務應能由 AI 代理通過運行 chmod、rm 等 shell 指令在 1 次迭代內完成。

請以標準 Markdown 格式輸出，並在報告最末端提供一個 `### 📅 待辦修復事項` 區段，只放置符合 Lobster 格式的待辦清單，不要有額外解釋。
"""
            logger.info(f"🧠 嘗試使用金鑰選項 {idx+1}/{len(keys_to_try)} 呼叫 Gemini 分析...")
            response = model.generate_content(prompt)
            report_content = response.text.strip()
            
            # 解析 TODO 事項
            for line in report_content.splitlines():
                m = re.match(r"^[-*]\s+\[\s*\]\s+(\[Security\].*)", line)
                if m:
                    todos.append(m.group(1).strip())
            
            success = True
            logger.info("✅ Gemini 安全大腦分析成功！")
            break
        except Exception as e:
            logger.warning(f"⚠️ 金鑰選項 {idx+1} 呼叫失敗: {e}")
            
    # ── 本地自癒降級引擎 (Local Self-Healing Fallback) ──
    if not success:
        logger.warning("🚨 所有 API 金鑰額度皆已耗盡或失效。啟動本地白帽資安防禦引擎，自動生成安全 TODO！")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        md = [
            f"# 🛡️ AgentOS 每日安全審計報告 (本地降級自癒模式)",
            f"> **安全顧問**：白帽駭客防禦系統 (Local Rule Engine)  ",
            f"> **生成時間**：`{now_str}`  ",
            f"> **狀態**：🔴 檢測到資安威脅 (已自動為 Lobster 產生修復待辦事項)",
            "",
            "---",
            "",
            "## 🔍 本地資安檢測事實彙整",
            ""
        ]
        
        # 1. 權限問題
        md.append("### 🔑 1. 敏感設定檔權限漏洞 (.env Permissions)")
        if facts["file_permissions"]:
            md.append("以下敏感檔案的權限過於寬鬆，可能遭同主機其他使用者或服務越權存取：")
            for item in facts["file_permissions"]:
                md.append(f"*   **檔案**：`{item['path']}` (當前權限：`{item['permission']}`，建議：`600`)")
                todos.append(f"[Security] 將 {item['path']} 檔案權限修正為 600 (-rw-------)")
        else:
            md.append("✅ 未檢測到敏感設定檔權限過於寬鬆的問題。")
        md.append("")
        
        # 2. 開放連接埠
        md.append("### 🌐 2. 外部暴露連接埠 (Exposed Port Listeners)")
        if facts["open_ports"]:
            md.append("以下連接埠綁定於 `0.0.0.0` 或所有網路介面，在未設定外部防火牆（如 Oracle Cloud Security List）的情況下，可能暴露於網際網路：")
            for item in facts["open_ports"]:
                md.append(f"*   **連接埠**：`{item['port']}` (進程：`{item['process']}`，綁定：`{item['address']}`)  ")
                md.append(f"    *風險程度*：**{item['severity']}**")
                # 開放連接埠建議進行安全檢索
                todos.append(f"[Security] 檢查連接埠 {item['port']} ({item['process']}) 綁定安全性與雲端防火牆規則")
        else:
            md.append("✅ 未檢測到高風險暴露端口。")
        md.append("")
        
        # 3. 備份洩漏
        md.append("### 💾 3. 殘留備份與金鑰檔案 (.bak File Check)")
        if facts["exposed_secrets"]:
            md.append("發現以下歷史備份檔案，可能殘留舊版明文金鑰：")
            for item in facts["exposed_secrets"]:
                md.append(f"*   **檔案**：`{item['path']}` (風險：可能洩漏過期金鑰紀錄)")
                todos.append(f"[Security] 安全移除殘留備份檔案 {item['path']}")
        else:
            md.append("✅ 未發現敏感備份檔案洩漏。")
            
        md.append("")
        md.append("---")
        md.append("")
        md.append("### 📅 待辦修復事項")
        for t in todos:
            md.append(f"- [ ] {t}")
            
        report_content = "\n".join(md)
        
    return report_content, todos

# ── 3. 更新專案狀態與同步中央看板 ───────────────────────────────────────────

def update_security_status_md(report: str, todos: list[str]):
    """將 TODO 事項注入 security-audit 的 STATUS.md 中"""
    if not STATUS_MD.exists():
        logger.error(f"找不到專案狀態檔: {STATUS_MD}")
        return
        
    content = STATUS_MD.read_text(encoding="utf-8")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 1. 更新 Last Status & Last Updated
    content = re.sub(
        r"\|\s*\*\*Last Status\*\*\s*\|\s*([^|]+)\|",
        f"| **Last Status** | 🛡️ Audit Completed - {len(todos)} Action Items |",
        content
    )
    content = re.sub(
        r"\|\s*\*\*Last Updated\*\*\s*\|\s*([^|]+)\|",
        f"| **Last Updated** | {now_str} |",
        content
    )
    
    # 2. 更新 Todo List
    todo_section_lines = ["## 📅 Todo List"]
    if todos:
        for t in todos:
            todo_section_lines.append(f"- [ ] {t}")
    else:
        todo_section_lines.append("- [ ] Define objectives")
        todo_section_lines.append("- [ ] Break work into milestones")
        todo_section_lines.append("- [ ] Execute and report progress")
        
    # 進行 Todo List 段落置換
    pattern = re.compile(r"## 📅 Todo List.*?(?=## 🧠 Working Summary)", re.DOTALL)
    new_todo_content = "\n".join(todo_section_lines) + "\n\n"
    content = pattern.sub(new_todo_content, content)
    
    # 3. 記錄活動日誌
    log_entry = f"- `{now_str}` 🛡️ **[AUDIT]** 白帽駭客掃描完成，產出安全漏洞任務 {len(todos)} 項。"
    if "<!-- LOG_START -->" in content:
        content = content.replace("<!-- LOG_START -->", f"<!-- LOG_START -->\n{log_entry}", 1)
        
    STATUS_MD.write_text(content, encoding="utf-8")
    logger.info(f"✅ 成功將 {len(todos)} 項安全任務注入至 security-audit STATUS.md")

def main():
    logger.info("🛡️ 啟動白帽駭客每日安全監控與自動化審計...")
    
    # 1. 執行實體資安掃描
    facts = {
        "file_permissions": scan_file_permissions(),
        "open_ports": scan_open_ports(),
        "exposed_secrets": scan_exposed_secrets(),
        "scan_time": datetime.now(timezone.utc).isoformat()
    }
    
    total_threats = len(facts["file_permissions"]) + len(facts["open_ports"]) + len(facts["exposed_secrets"])
    logger.info(f"📊 掃描完成：共發現 {total_threats} 個潛在安全疑慮項目。")
    
    # 1.5. 執行 detect_secrets_scanner
    try:
        scripts_dir = HOME / "agentmanager" / "scripts"
        logger.info("🛡️ 啟動 detect-secrets 預檢防漏掃描...")
        subprocess.run(
            [sys.executable, str(scripts_dir / "detect_secrets_scanner.py")],
            check=False, capture_output=False
        )
    except Exception as e:
        logger.error(f"❌ detect-secrets 掃描失敗: {e}")
    
    # 2. 呼叫 Gemini 進行漏洞分析與 TODO 產生
    report, todos = run_security_analysis(facts)
    
    # 3. 寫入白帽駭客報告
    REPORT_MD.write_text(report, encoding="utf-8")
    logger.info(f"💾 安全審計報告已寫入: {REPORT_MD}")
    
    # 4. 更新 security-audit 的 STATUS.md
    update_security_status_md(report, todos)
    
    # 5. 強制執行 sync_task_board.py 重建中央 TASK_BOARD.md
    try:
        scripts_dir = HOME / "agentmanager" / "scripts"
        subprocess.run(
            [sys.executable, str(scripts_dir / "sync_task_board.py"), "--reset"],
            check=True, capture_output=True
        )
        logger.info("🔄 中央 TASK_BOARD.md 已完成同步與重置，安全待辦事項已就緒！")
    except Exception as e:
        logger.error(f"❌ 同步中央看板失敗: {e}")
        
    # 6. 發送 Telegram 警報
    if todos:
        alert_msg = (
            f"🚨 *[白帽駭客安全威脅通報]*\n\n"
            f"本機每日資安掃描已完成。共發現 *{len(todos)}* 項安全威脅！\n"
            f"詳細安全報告已輸出至 `WHITE_HAT_REPORT.md`。\n\n"
            f"🔧 *自律修復已接管*：\n"
            f"安全修復代辦事項已自動注入中央 `TASK_BOARD.md` 的 `security-audit` 專案中，"
            f"**Lobster 執行引擎**將會在下一次自律推進中自動接手進行一鍵修復！"
        )
        send_telegram_alert(alert_msg)
    else:
        logger.info("✅ 系統完全合規安全，未發現任何威脅！")

if __name__ == "__main__":
    main()
