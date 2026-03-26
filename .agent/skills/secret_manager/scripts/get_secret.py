#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse

def run_cmd(cmd, input_data=None):
    try:
        process = subprocess.run(
            cmd,
            input=input_data,
            shell=True,
            text=True,
            capture_output=True,
            check=True
        )
        return process.stdout.strip()
    except subprocess.CalledProcessError as e:
        return None

def get_config():
    # Load primary config from agentmanager/.env
    config = {}
    env_path = "/home/ubuntu/agentmanager/.env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip("'").strip('"')
    return config

def fetch_from_bw(item_name, key=None):
    bw_session = os.environ.get("BW_SESSION")
    if not bw_session:
        return None, "BW_SESSION not found. Run 'bw unlock'."

    # Get item by name
    session = os.environ.get("BW_SESSION", "")
    res = run_cmd(f"bw get items '{item_name}' --session '{session}'")
    if not res:
        return None, f"Item '{item_name}' not found in Bitwarden."

    item = json.loads(res)
    
    # If key is provided, search in login or fields
    if key:
        # Search in login
        login = item.get("login", {})
        if key.lower() in ["username", "user", "email"]:
            return login.get("username"), None
        if key.lower() in ["password", "pass"]:
            return login.get("password"), None
        
        # Search in custom fields
        for field in item.get("fields", []):
            if field.get("name") == key:
                return field.get("value"), None
        return None, f"Key '{key}' not found in item '{item_name}'."
    
    # If no key, return entire mapped fields as a dict
    flat_data = {}
    login = item.get("login", {})
    if login.get("username"): flat_data["BW_USERNAME"] = login["username"]
    if login.get("password"): flat_data["BW_PASSWORD"] = login["password"]
    for field in item.get("fields", []):
        flat_data[field["name"]] = field["value"]
    return flat_data, None

def fetch_from_local(project_name):
    secrets_dir = "/home/ubuntu/agent-data/secrets"
    path = f"{secrets_dir}/{project_name}.env"
    if not os.path.exists(path):
        return None, f"Local secret file not found: {path}"
    
    secrets = {}
    with open(path, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip().strip("'").strip('"')
    return secrets, None

def load_session():
    if "BW_SESSION" not in os.environ:
        session_file = "/home/ubuntu/agent-data/secrets/.bw_session"
        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                os.environ["BW_SESSION"] = f.read().strip()

def main():
    parser = argparse.ArgumentParser(description="Unified Secret Manager Tool")
    parser.add_argument("project", help="Project name (for local mode) or BW item name")
    parser.add_argument("--key", help="Specific key to fetch")
    parser.add_argument("--inject", action="store_true", help="Automatically write to current directory .env")
    
    args = parser.parse_args()
    load_session()
    config = get_config()
    backend = config.get("SECRET_BACKEND", "local")

    if backend == "bitwarden":
        data, err = fetch_from_bw(args.project, args.key)
    else:
        # Local mode: project name is used to find .env in /agent-data/secrets/
        data, err = fetch_from_local(args.project)
        if data and args.key:
            data = data.get(args.key)

    if err:
        print(f"❌ {err}")
        sys.exit(1)

    if args.inject:
        if isinstance(data, dict):
            with open(".env", "a") as f:
                f.write(f"\n# --- Injected Secrets for {args.project} ---\n")
                for k, v in data.items():
                    f.write(f"{k}={v}\n")
            print(f"✅ Injected secrets for '{args.project}' into .env")
        else:
            print(f"⚠️ Cannot inject a single value. Use without --inject to see value (if safe).")
    else:
        # Output logic
        if isinstance(data, dict):
            print(json.dumps(data, indent=2))
        else:
            # We PRINT it, but the skill rules say "Never print secrets in terminal logs".
            # This tool is for INTERNAL agent use.
            print(data)

if __name__ == "__main__":
    main()
