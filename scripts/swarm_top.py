#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone

# --- Configuration ---
PULSE_FILE = Path("/dev/shm/leopardcat-swarm/pulse.json")
REFRESH_INTERVAL = 2 # Seconds

# --- UI Assets (Colors & Icons) ---
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"
C_CLEAR = "\033[H\033[J"

ICON_BUSY = "🔥"
ICON_IDLE = "💤"
ICON_ERROR = "💥"
ICON_BEATS = ["💓", "💗", "💖", "💝"]

def format_time(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts)
        diff = (datetime.now(timezone.utc) - dt).total_seconds()
        if diff < 60:
            return f"{int(diff)}s ago"
        return dt.strftime("%H:%M:%S")
    except:
        return "?"

def get_status_ui(status: str):
    if status == "active":
        return f"{C_GREEN}ACTIVE{C_END}", "🟢", ICON_BUSY
    if status == "error":
        return f"{C_RED}ERROR {C_END}", "🔴", ICON_ERROR
    return f"{C_YELLOW}IDLE  {C_END}", "🟡", ICON_IDLE

def render_board():
    beat_idx = int(time.time()) % len(ICON_BEATS)
    ts_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    output = []
    output.append(f"{C_CLEAR}{C_BOLD}{C_BLUE}🐾 LEOPARD-CAT SWARM (LCS) MONITOR{C_END} {ICON_BEATS[beat_idx]}")
    output.append(f"Global Pulse: {ts_now} | Heartbeat: OK")
    output.append("=" * 80)
    output.append(f"{'AGENT NAME':<18} {'STATE':<12} {'PID':<8} {'T-UPDATED':<12} {'CURRENT TASK'}")
    output.append("-" * 80)

    if not PULSE_FILE.exists():
        output.append(f"{C_YELLOW}Waiting for swarm heartbeat sync... (Shared Memory Empty){C_END}")
    else:
        try:
            pulse_data = json.loads(PULSE_FILE.read_text())
            for agent, info in pulse_data.items():
                state_text, dot, icon = get_status_ui(info.get("status", "unknown"))
                task = info.get("task", "None")
                if len(task) > 40: task = task[:37] + "..."
                
                output.append(f"{agent:<18} {state_text} {info.get('pid', 'N/A'):<8} {format_time(info.get('timestamp', '')): <12} {icon} {task}")
        except Exception as e:
            output.append(f"{C_RED}System Error reading pulse board: {e}{C_END}")

    output.append("-" * 80)
    output.append(f"{C_BLUE}Data Strategy:{C_END} Swarm Pulse Board [In-Memory Cache]")
    output.append(f"Refresh: {REFRESH_INTERVAL}s | Ctrl+C to Exit")
    
    print("\n".join(output))

if __name__ == "__main__":
    try:
        while True:
            render_board()
            time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Monitor detached. LCS remains active in background.{C_END}")
