#!/usr/bin/env python3
import os
import sys

def get_input(prompt, default=None):
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()

def main():
    print("🚀 Antigravity Agent OS - Initial Setup")
    print("---------------------------------------")
    print("This script will generate your .env file.\n")

    if os.path.exists(".env"):
        confirm = input(".env already exists. Overwrite? (y/N): ").lower()
        if confirm != 'y':
            print("Setup cancelled.")
            return

    # Gather inputs
    agent_data_root = get_input("Data Root Path (e.g., /home/ubuntu/agent-data)", "/home/ubuntu/agent-data")
    github_token = get_input("GitHub Token")
    tg_token = get_input("Telegram Bot Token")
    tg_id = get_input("Telegram Authorized ID (User/Channel)")
    gemini_key = get_input("Gemini API Key")
    cc_repo = get_input("Data Repository (GitHub Name, e.g., user/my-agent-data)", "alston-personal/my-agent-data")

    # Generate content
    content = f"""# 📂 Data Layer Configuration
AGENT_DATA_ROOT={agent_data_root}

# 🔑 Secrets & Tokens
GITHUB_TOKEN={github_token}
TELEGRAM_BOT_TOKEN={tg_token}
TELEGRAM_CHANNEL_ID={tg_id}

# 🧠 AI Configuration
GEMINI_API_KEY={gemini_key}
COMMAND_CENTER_REPO={cc_repo}

# 🧠 Advanced
KNOWLEDGE_ROOT=/home/ubuntu/.gemini/antigravity/knowledge
"""

    with open(".env", "w", encoding="utf-8") as f:
        f.write(content)

    print("\n✅ .env file generated successfully!")
    print("Next step: Run 'python3 scripts/run_workflow.py status' to verify connectivity.")

if __name__ == "__main__":
    main()
