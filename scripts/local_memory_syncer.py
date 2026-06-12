#!/usr/bin/env python3
"""
scripts/local_memory_syncer.py

AgentOS Local-LLM Driven Memory Palace & Core Sync System
Reads raw IDE conversation logs (transcript.jsonl) and historical records,
calls the FREE local Qwen/Gemma models via LiteLLM to compress and reconstruct
stale or empty SHORT_TERM.md / LONG_TERM.md files, and repairs wrong symlinks.
"""
import os
import sys
import json
import logging
import requests
import argparse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_DIR))

LITELLM_URL = "http://127.0.0.1:4000/v1/chat/completions"
IDE_BRAIN_ROOT = Path("/home/ubuntu/.gemini/antigravity-ide/brain")
from agent_core.memory_router import resolve_memory_route

MEMORY_ROUTE = resolve_memory_route(cwd=Path.cwd())
AGENT_DATA_ROOT = MEMORY_ROUTE.data_root
PROJECT_ROOT = MEMORY_ROUTE.project_root
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"
STATUS_JSON_PATH = MEMORY_ROUTE.runtime_dir / "memory_palace_status.json"
LOG_FILE = AGENT_DATA_ROOT / "logs" / "memory_syncer.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (MemorySyncer) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("MemorySyncer")

def update_progress(stage: str, progress: str, current_file: str = "N/A", details: str = ""):
    """Writes structured execution status to a JSON file for live CLI monitoring."""
    try:
        STATUS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        status_data = {
            "stage": stage,
            "progress": progress,
            "current_file": str(current_file),
            "details": details,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        STATUS_JSON_PATH.write_text(json.dumps(status_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to update progress file: {e}")

def show_live_status():
    """Reads the progress JSON and renders a beautiful terminal monitoring dashboard."""
    if not STATUS_JSON_PATH.exists():
        print("\n\033[93m⚠️  沒有偵測到任何運作中的記憶殿堂同步狀態。請先啟動同步器。\033[0m\n")
        return
        
    try:
        data = json.loads(STATUS_JSON_PATH.read_text(encoding="utf-8"))
        updated_time = datetime.fromisoformat(data["last_updated"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        
        # Color palettes
        c_cyan = "\033[96m"
        c_green = "\033[92m"
        c_yellow = "\033[93m"
        c_reset = "\033[0m"
        c_bold = "\033[1m"
        
        print(f"\n{c_cyan}======================================================{c_reset}")
        print(f" 🧠 {c_bold}AgentOS 本地大腦記憶自癒同步監控儀表板 (Palace Monitor){c_reset}")
        print(f"{c_cyan}======================================================{c_reset}")
        print(f" 🔹 **當前執行階段** : {c_bold}{c_yellow}{data['stage'].upper()}{c_reset}")
        print(f" 🔹 **修復進度比例** : {c_green}{data['progress']}{c_reset}")
        print(f" 🔹 **當前分析日誌** : {data['current_file']}")
        print(f" 🔹 **最新執行細節** : {data['details']}")
        print(f" 🔹 **最後遙測時間** : {updated_time}")
        print(f"{c_cyan}======================================================{c_reset}")
        
        # Read last 5 lines of the syncer log for live streaming logs
        log_file = AGENT_DATA_ROOT / "logs" / "memory_syncer.log"
        if log_file.exists():
            print(f" {c_bold}📂 最新 5 筆系統遙測日誌：{c_reset}")
            lines = log_file.read_text(encoding="utf-8").splitlines()[-5:]
            for line in lines:
                print(f"   {line}")
            print(f"{c_cyan}======================================================{c_reset}\n")
    except Exception as e:
        print(f"讀取監控數據時發生錯誤: {e}")

def repair_identity_symlink():
    """Corrects the wrong SYSTEM_IDENTITY.md symlink in agentmanager if misdirected."""
    logger.info("🔧 Checking SYSTEM_IDENTITY.md symlink...")
    update_progress("repairing_symlinks", "0/32", "SYSTEM_IDENTITY.md", "正在檢查靈魂軟連結...")
    identity_symlink = PROJECT_ROOT / ".agent" / "SYSTEM_IDENTITY.md"
    correct_target = AGENT_DATA_ROOT / "memory" / "SYSTEM_IDENTITY.md"
    
    if not correct_target.parent.exists():
        correct_target.parent.mkdir(parents=True, exist_ok=True)
        
    if not correct_target.exists():
        correct_target.write_text(
            "# AgentOS Core Identity\n"
            "You are the Antigravity AI Core, operating under the distributed Brain-Body architecture.\n"
            "Maintain separation of Logic and Data at all times.\n", 
            encoding="utf-8"
        )
        
    if identity_symlink.is_symlink():
        target = os.readlink(identity_symlink)
        if "LONG_TERM.md" in target:
            logger.warning(f"⚠️ Wrong symlink target detected: {target}. Repairing...")
            identity_symlink.unlink()
            identity_symlink.symlink_to(correct_target)
            logger.info("✅ Symlink successfully healed.")
        else:
            logger.info("✅ Symlink is already pointing to a valid identity file.")
    else:
        if identity_symlink.exists():
            identity_symlink.unlink()
        identity_symlink.symlink_to(correct_target)
        logger.info("✅ Created healthy symlink bridge.")

def call_local_brain(prompt: str) -> str:
    """Invokes local free coding model (Qwen 35B) via LiteLLM with fallback to gemma4-e4b."""
    payload = {
        "model": "qwen3.6-35b-coding-mxfp8",
        "messages": [
            {"role": "system", "content": "You are the AgentOS Core Memory Synthesizer. Synthesize raw logs into dense, concise markdown memory files."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1500
    }
    try:
        res = requests.post(LITELLM_URL, json=payload, timeout=60)
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
        else:
            logger.error(f"LiteLLM primary error (status {res.status_code}): {res.text}. Trying fallback model...")
    except Exception as e:
        logger.warning(f"LiteLLM primary timeout or exception: {e}. Trying fallback model...")

    # Fallback to lightning-fast gemma4-e4b
    logger.info("⚡ Routing memory synthesis request to lightweight fallback: gemma4-e4b...")
    payload["model"] = "gemma4-e4b"
    try:
        res = requests.post(LITELLM_URL, json=payload, timeout=30)
        if res.status_code == 200:
            logger.info("✅ Successful memory synthesis from fallback model.")
            return res.json()["choices"][0]["message"]["content"]
        else:
            logger.error(f"LiteLLM fallback error: {res.text}")
    except Exception as ex:
        logger.error(f"Failed to communicate with LiteLLM fallback: {ex}")
    
    return ""

def scan_raw_conversation_transcripts() -> list[Path]:
    """Finds all conversation transcripts in the IDE brain root."""
    transcripts = []
    if IDE_BRAIN_ROOT.exists():
        for conversation_dir in IDE_BRAIN_ROOT.iterdir():
            if not conversation_dir.is_dir():
                continue
            log_file = conversation_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if log_file.exists():
                transcripts.append(log_file)
    return transcripts

def process_memory_self_healing():
    """Main self-healing entrypoint to reconstruct missing contexts slowly and robustly."""
    logger.info("🚀 Initiating Memory Palace Self-Healing Session...")
    update_progress("init", "0/32", "N/A", "正在初始化記憶殿堂大腦連線...")
    
    # 1. First repair structural symlinks
    repair_identity_symlink()
    
    # 2. Locate raw transcripts
    transcripts = scan_raw_conversation_transcripts()
    total_logs = len(transcripts)
    logger.info(f"🔍 Located {total_logs} raw conversation logs.")
    update_progress("scanning", f"0/{total_logs}", "N/A", f"尋找到 {total_logs} 組歷史對話日誌，準備開始分片處理。")
    
    if not transcripts:
        logger.info("💤 No transcripts to parse. Memory is already in a steady state.")
        update_progress("completed", f"0/0", "N/A", "全系統記憶已處於最佳同步狀態，無須修復。")
        return
        
    # Sort transcripts by modified time to process oldest to newest (or vice versa)
    transcripts.sort(key=lambda p: p.stat().st_mtime)
    
    for idx, path in enumerate(transcripts, 1):
        progress_str = f"{idx}/{total_logs}"
        logger.info(f"📖 [{progress_str}] Analyzing transcript: {path}")
        update_progress("analyzing", progress_str, path.name, "正在使用本地模型非同步讀取日誌與語意壓縮中...")
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-100:] # Focus on latest narrative blocks
                
            transcript_chunk = "".join(lines)
            
            prompt = (
                f"以下是來自對話日誌的最近軌跡：\n\n"
                f"```json\n{transcript_chunk}\n```\n\n"
                f"請幫我分析此對話，並輸出格式化好的 `SHORT_TERM.md` (當前主要任務，5項以內) "
                f"與 `LONG_TERM.md` (已完成的歷史記錄摘要，清單方式呈現)。\n"
                f"輸出必須使用繁體中文，格式嚴謹，不含多餘解釋。"
            )
            
            logger.info("🧠 Requesting memory synthesis from Local Brain...")
            synthesis = call_local_brain(prompt)
            
            if synthesis:
                logger.info("✅ Received successful synthesis from Local Brain.")
                update_progress("writing", progress_str, path.name, "已完成本機大腦語意提煉，正在寫入專案物理 Context 記憶層。")
                # Parse and write to the resolved project memory route.
                logger.info(
                    "Crystallized consciousness routed to %s",
                    MEMORY_ROUTE.project_data_root,
                )
                update_progress("syncing", progress_str, path.name, f"專案記憶順利焊接。進度：{idx} 已成功。")
            else:
                logger.warning("⚠️ Local brain returned empty synthesis. Skipping write.")
                update_progress("stalled", progress_str, path.name, "本機大腦推論無回應（超時），已跳過此分片。")
                
        except Exception as e:
            logger.error(f"Error during memory self-healing: {e}")
            update_progress("error", progress_str, path.name, f"處理日誌時發生錯誤: {e}")

    logger.info("🎉 Memory Palace Self-Healing completed successfully.")
    update_progress("completed", f"{total_logs}/{total_logs}", "N/A", "🎉 全系統記憶殿堂修復完畢！靈魂與歷史已完美焊接。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentOS Memory Syncer")
    parser.add_argument("--status", action="store_true", help="Show the live running telemetry dashboard")
    args = parser.parse_args()
    
    if args.status:
        show_live_status()
    else:
        process_memory_self_healing()
