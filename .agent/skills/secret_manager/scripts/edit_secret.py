#!/usr/bin/env python3
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
        return None

def get_item_by_name(item_name):
    # Use --session explicitly to avoid interactive prompts
    session = os.environ.get("BW_SESSION", "")
    res = run_cmd(f"bw list items --search '{item_name}' --session '{session}'")
    if not res:
        return None
    items = json.loads(res)
    # Filter for exact name match
    for item in items:
        if item.get("name") == item_name:
            return item
    return None

def checkout(item_name):
    item = get_item_by_name(item_name)
    if not item:
        print(f"❌ Item '{item_name}' not found in Bitwarden.")
        return

    temp_path = f"/tmp/bw_edit_{item_name}.env"
    with open(temp_path, "w") as f:
        f.write(f"# --- Bitwarden Edit: {item_name} (ID: {item['id']}) ---\n")
        f.write(f"# Do NOT change the ID line below if you want to update the original item.\n")
        f.write(f"BW_ITEM_ID={item['id']}\n\n")
        
        login = item.get("login", {})
        if login.get("username"):
            f.write(f"BW_USERNAME={login['username']}\n")
        if login.get("password"):
            f.write(f"BW_PASSWORD={login['password']}\n")
            
        for field in item.get("fields", []):
            f.write(f"{field['name']}={field['value']}\n")
            
    print(f"✅ Item '{item_name}' checked out to: {temp_path}")
    print(f"👉 Edit the file: nano {temp_path}")
    print(f"👉 When done, run: ./edit_secret.py checkin {item_name}")

def checkin(item_name):
    temp_path = f"/tmp/bw_edit_{item_name}.env"
    if not os.path.exists(temp_path):
        print(f"❌ Temporary file not found: {temp_path}")
        return

    secrets = {}
    item_id = None
    with open(temp_path, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'").strip('"')
                if k == "BW_ITEM_ID":
                    item_id = v
                else:
                    secrets[k] = v

    if not item_id:
        print("❌ Could not find BW_ITEM_ID in the temp file. Aborting.")
        return

    # Get original item to preserve metadata
    session = os.environ.get("BW_SESSION", "")
    orig_res = run_cmd(f"bw get items '{item_id}' --session '{session}'")
    if not orig_res:
        print(f"❌ Could not retrieve original item with ID {item_id}.")
        return
    
    item = json.loads(orig_res)
    
    # Update fields
    new_fields = []
    login = item.get("login", {})
    
    for k, v in secrets.items():
        if k == "BW_USERNAME":
            login["username"] = v
        elif k == "BW_PASSWORD":
            login["password"] = v
        else:
            new_fields.append({
                "name": k,
                "value": v,
                "type": 1  # Hidden/Secure
            })
            
    item["login"] = login
    item["fields"] = new_fields
    
    # Sanitize for update (Remove read-only fields)
    for k in ["revisionDate", "creationDate", "deletedDate", "archivedDate", "organizationId", "collectionIds"]:
        if k in item: del item[k]

    # Push update
    json_data = json.dumps(item)
    encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('utf-8')
    session = os.environ.get("BW_SESSION", "")
    res = run_cmd(f"bw edit items {item_id} --session '{session}'", input_data=encoded_data)
    
    if res:
        print(f"✅ Item '{item_name}' (ID: {item_id}) successfully updated in Bitwarden.")
        os.remove(temp_path)
        print(f"🗑️ Temporary file deleted.")
    else:
        print("❌ Update failed.")

def load_session():
    # Attempt to load from file if not in environment
    if "BW_SESSION" not in os.environ:
        session_file = "/home/ubuntu/agent-data/secrets/.bw_session"
        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                os.environ["BW_SESSION"] = f.read().strip()
    return os.environ.get("BW_SESSION")

def main():
    parser = argparse.ArgumentParser(description="Bitwarden Edit-Sync Workflow")
    parser.add_argument("action", choices=["checkout", "checkin"], help="Action to perform")
    parser.add_argument("name", help="Name of the Bitwarden item")
    
    args = parser.parse_args()
    
    session = load_session()
    
    if not session:
        print("❌ Error: BW_SESSION is not set. Run 'bw unlock --raw > /home/ubuntu/agent-data/secrets/.bw_session'.")
        sys.exit(1)

    # Note: Subprocess.run with shell=True inherits os.environ, 
    # but explicit --session is more reliable in some Linux environments.

    if args.action == "checkout":
        checkout(args.name)
    elif args.action == "checkin":
        checkin(args.name)

if __name__ == "__main__":
    main()
