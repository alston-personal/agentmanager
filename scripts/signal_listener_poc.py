#!/usr/bin/env python3
import signal
import time
import sys
import json
from pathlib import Path

# --- Configuration ---
PULSE_FILE = Path("/dev/shm/leopardcat-swarm/pulse.json")
INBOX_FILE = Path("/home/ubuntu/agent-data/memory/INBOX_LCS_WORKER.md")
MY_AGENT_NAME = "LCS-Worker-POC"

class SwarmAgent:
    def __init__(self):
        self.running = True
        self.task = "Awaiting instructions..."
        self.register_pulse()
        
        # 🔔 Core Signal Registration
        # 當收到 SIGUSR1 時，不要結束程式，而是執行 handle_interruption 函式
        signal.signal(signal.SIGUSR1, self.handle_interruption)
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)

    def register_pulse(self):
        """把自己的 PID 註冊到 Shared Memory (讓 Swarm Monitor 抓得到)"""
        PULSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if PULSE_FILE.exists():
            try:
                data = json.loads(PULSE_FILE.read_text())
            except: pass
            
        data[MY_AGENT_NAME] = {
            "task": self.task,
            "status": "active",
            "pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        PULSE_FILE.write_text(json.dumps(data, indent=2))
        print(f"[{MY_AGENT_NAME}] Registered with PID: {os.getpid()}")

    def handle_interruption(self, signum, frame):
        """事件驅動的核心：被 Signal 喚醒時立刻中斷手邊工作去檢查 Inbox"""
        print(f"\n⚡ [INTERRUPT] Received SIGUSR1 ({signum}). Pausing current task: '{self.task}'")
        print("🔍 Checking Inbox for critical updates...")
        
        if INBOX_FILE.exists():
            msg = INBOX_FILE.read_text()
            print(f"📨 [NEW MESSAGE]\n{'-'*40}\n{msg}\n{'-'*40}")
            print("🧠 Internalizing new context (Context Window updated).")
            # 在這裡，真實的 Agent 會把這段新訊息塞進 Prompt 裡。
        else:
            print("📭 Inbox empty. False alarm.")
            
        print("▶️ Resuming work...\n")

    def shutdown(self, signum, frame):
        self.running = False
        print("\n[SHUTDOWN] Unregistering from swarm...")

    def work_loop(self):
        """模擬 Agent 日常發呆或是生圖等漫長的工作迴圈"""
        import os
        from datetime import datetime, timezone
        counter = 0
        while self.running:
            self.task = f"Generating Artwork Batch... (Step {counter})"
            self.register_pulse()
            print(f"[{os.getpid()}] Working: {self.task} (Waiting for signals...)")
            time.sleep(5)  # 模擬耗時操作。如果在 sleep 期間收到信號，會立刻被喚醒。
            counter += 1

if __name__ == "__main__":
    import os
    from datetime import datetime, timezone
    print(f"🚀 Starting {MY_AGENT_NAME} Agent POC...")
    print(f"💡 You can test this by running in another terminal: kill -SIGUSR1 {os.getpid()}")
    agent = SwarmAgent()
    agent.work_loop()
