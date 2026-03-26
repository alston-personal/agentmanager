import os
import sys
import json
import subprocess
import argparse
import base64

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
        print(f"❌ Command failed: {e.stderr}")
        sys.exit(1)

def parse_env(file_path):
    secrets = {}
    if not os.path.exists(file_path):
        print(f"❌ .env file not found: {file_path}")
        sys.exit(1)
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes if present
                value = value.strip().strip("'").strip('"')
                secrets[key.strip()] = value
    return secrets

def migrate_to_bw(name, secrets):
    print(f"📦 Preparing Bitwarden item: {name}")
    
    # Get template
    template_json = run_cmd("bw get template item")
    template = json.loads(template_json)
    
    template["name"] = name
    template["type"] = 1  # Login
    
    # Initialize login object
    login_template_json = run_cmd("bw get template item.login")
    template["login"] = json.loads(login_template_json)
    template["login"]["username"] = ""
    template["login"]["password"] = ""
    template["login"]["totp"] = None
    template["login"]["uris"] = []
    
    fields = []
    for key, value in secrets.items():
        # Handle special fields
        low_key = key.lower()
        if any(x in low_key for x in ['email', 'user', 'username']):
            template["login"]["username"] = value
        elif any(x in low_key for x in ['password', 'pass']):
            template["login"]["password"] = value
        else:
            # Custom fields
            fields.append({
                "name": key,
                "value": value,
                "type": 1  # Hidden/Secure field
            })
    
    template["fields"] = fields
    
    # Sanitize: Remove null fields that might cause parsing errors in some CLI versions
    keys_to_remove = ["revisionDate", "creationDate", "deletedDate", "archivedDate", "organizationId", "collectionIds"]
    for k in keys_to_remove:
        if k in template:
            del template[k]

    # Create item
    print(f"🚀 Creating item in vault...")
    json_data = json.dumps(template)
    encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
    result = run_cmd("bw create item", input_data=encoded_data)
    print(f"✅ Success! Item created.")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate .env secrets to Bitwarden")
    parser.add_argument("env_file", help="Path to the .env file")
    parser.add_argument("--name", required=True, help="Name of the Bitwarden item")
    
    args = parser.parse_args()
    
    if "BW_SESSION" not in os.environ:
        print("❌ Error: BW_SESSION is not set. Please run 'export BW_SESSION=$(bw unlock --raw)' first.")
        sys.exit(1)
        
    secrets = parse_env(args.env_file)
    if not secrets:
        print("⚠️ No secrets found in .env file.")
        sys.exit(0)
        
    migrate_to_bw(args.name, secrets)
