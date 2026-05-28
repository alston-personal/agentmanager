#!/usr/bin/env python3
"""
Antigravity AgentOS Secrets Auditing & Centralization Tool
Ensures compliance with Logic/Data Separation architecture by migrating legacy physical
secrets (.env, credentials, cookies, tokens) to the centralized data layer and establishing symlinks.
"""
import os
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SecretsAudit")

AGENT_DATA_SECRETS = Path("/home/ubuntu/agent-data/secrets")
WORKSPACES_SECRETS_MAP = {
    # File to centralize -> target path under data/secrets
    "/home/ubuntu/y2help-web/backend/.env": AGENT_DATA_SECRETS / "y2help-web.env",
    "/home/ubuntu/n8n-automation/.env": AGENT_DATA_SECRETS / "n8n-automation.env",
    "/home/ubuntu/youtube-ai-manager/client_secret.json": AGENT_DATA_SECRETS / "youtube-ai-manager/client_secret.json",
    "/home/ubuntu/youtube-ai-manager/token_gamelife.json": AGENT_DATA_SECRETS / "youtube-ai-manager/token_gamelife.json",
    "/home/ubuntu/youtube-ai-manager/token_virtualworld.json": AGENT_DATA_SECRETS / "youtube-ai-manager/token_virtualworld.json",
    "/home/ubuntu/youtube-ai-manager/cookies.txt": AGENT_DATA_SECRETS / "youtube-ai-manager/cookies.txt",
}

def process_file(source_path_str, target_path):
    source_path = Path(source_path_str)
    
    # 1. Skip if source file doesn't exist
    if not source_path.exists() and not source_path.is_symlink():
        logger.info(f"⏭️  File {source_path} does not exist. Skipping.")
        return
        
    # 2. Check if already a symlink
    if source_path.is_symlink():
        dest = os.readlink(source_path)
        logger.info(f"✅ Already linked: {source_path} -> {dest}")
        return

    logger.info(f"🔍 Found physical credential file: {source_path}")
    
    # 3. Create target directory
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 4. If target doesn't exist, migrate/copy it
    if not target_path.exists():
        logger.info(f"📦 Migrating {source_path} to centralized vault {target_path}...")
        shutil.copy2(source_path, target_path)
        # Verify copied successfully
        if not target_path.exists():
            logger.error(f"❌ Failed to copy {source_path} to {target_path}")
            return
    else:
        logger.info(f"⚠️  Centralized file already exists @ {target_path}. Using existing.")

    # 5. Backup the original file just in case
    backup_path = source_path.with_name(source_path.name + ".bak")
    logger.info(f"💾 Backing up original to {backup_path}")
    if source_path.exists():
        if backup_path.exists():
            backup_path.unlink()
        source_path.rename(backup_path)

    # 6. Establish Symlink
    logger.info(f"🔗 Establishing symlink bridge: {source_path} -> {target_path}")
    try:
        source_path.symlink_to(target_path)
        logger.info(f"🎉 Successfully linked {source_path} to {target_path}!")
        # Clean up backup since symlink works
        if backup_path.exists():
            backup_path.unlink()
            logger.info("🗑️  Removed backup file.")
    except Exception as e:
        logger.error(f"❌ Failed to create symlink: {e}")
        # Restore backup
        if backup_path.exists():
            backup_path.rename(source_path)
            logger.warning("🔄 Restored backup file.")

def main():
    logger.info("🛡️  Starting AgentOS Global Secrets Auditing...")
    
    # Ensure agent-data secrets dir exists
    AGENT_DATA_SECRETS.mkdir(parents=True, exist_ok=True)
    
    for src, dst in WORKSPACES_SECRETS_MAP.items():
        process_file(src, dst)
        
    logger.info("🎉 Secrets Auditing Completed successfully!")

if __name__ == "__main__":
    main()
