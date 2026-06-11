#!/usr/bin/env python3
# ============================================================
# AgentOS Secrets Migrator & Extractor
# Scans local workspaces for .env files, extracts credentials,
# and consolidates them into ~/.agentos.secrets.
# ============================================================
import os
import re
from pathlib import Path

# Common keys that represent credentials
SECRET_PATTERNS = [
    r"TOKEN", r"KEY", r"SECRET", r"PASSWORD", r"PWD", r"AUTH", 
    r"ID", r"HOOK", r"URL", r"HASH", r"CREDENTIALS"
]

def load_keys_from_env(env_path: Path) -> dict:
    keys = {}
    if not env_path.exists():
        return keys
    
    try:
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            
            # Check if key matches secret patterns and has a non-placeholder value
            is_secret = any(re.search(pat, key, re.IGNORECASE) for pat in SECRET_PATTERNS)
            is_placeholder = any(p in val.lower() for p in ["your_", "placeholder", "dummy", "here", "todo", "change_me"])
            
            # We also ignore general path settings
            is_path = any(p in key.upper() for p in ["PATH", "DIR", "ROOT"])
            
            if is_secret and not is_placeholder and not is_path and val:
                keys[key] = val
    except Exception as e:
        print(f"⚠️ Error reading {env_path}: {e}")
    
    return keys

def main():
    home = Path.home()
    global_secrets_path = home / ".agentos.secrets"
    
    print("🔍 [Secrets Extractor] Scanning workspaces for credentials...")
    
    # 1. Load existing global secrets so we don't overwrite them
    all_secrets = {}
    if global_secrets_path.exists():
        print(f"📂 Loading existing global secrets from {global_secrets_path}")
        all_secrets = load_keys_from_env(global_secrets_path)
    
    # 2. Identify potential folders containing .env
    # We scan directories in the home directory
    scanned_count = 0
    extracted_count = 0
    
    for item in home.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            env_file = item / ".env"
            if env_file.exists():
                scanned_count += 1
                found_keys = load_keys_from_env(env_file)
                for k, v in found_keys.items():
                    if k not in all_secrets:
                        all_secrets[k] = v
                        extracted_count += 1
                        print(f"   ✨ Extracted [{k}] from {item.name}/.env")
                    elif all_secrets[k] != v:
                        print(f"   ℹ️  Duplicate [{k}] found in {item.name}/.env (keeping existing value)")

    # Also scan current directory
    local_env = Path(".env")
    if local_env.exists():
        found_keys = load_keys_from_env(local_env)
        for k, v in found_keys.items():
            if k not in all_secrets:
                all_secrets[k] = v
                extracted_count += 1
                print(f"   ✨ Extracted [{k}] from local .env")

    # 3. Write consolidated secrets to ~/.agentos.secrets
    if extracted_count > 0 or not global_secrets_path.exists():
        print(f"\n✍️ Writing consolidated secrets to {global_secrets_path}...")
        
        lines = [
            "# 🔐 Global Shared Secrets for AgentOS",
            "# Automatically consolidated by Secrets Extractor",
            ""
        ]
        
        for k, v in sorted(all_secrets.items()):
            lines.append(f"{k}={v}")
        
        global_secrets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"✅ Migration Complete. Total active keys: {len(all_secrets)}")
    else:
        print("\n☀️ No new secrets found to extract. ~/.agentos.secrets is already up to date.")

if __name__ == "__main__":
    main()
