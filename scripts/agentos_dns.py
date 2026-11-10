#!/usr/bin/env python3
"""
🌐 AgentOS DNS Manager (Cloudflare Automation)
Automates DNS record lifecycle (A, CNAME, TXT) for milkcat.org via Cloudflare API.
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

ENV_PATH = Path('/home/ubuntu/agentmanager/.env')

def load_env() -> dict[str, str]:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"\'')
    return env

def get_token() -> str:
    token = os.environ.get('CLOUDFLARE_API_TOKEN') or load_env().get('CLOUDFLARE_API_TOKEN')
    if not token:
        print("Error: CLOUDFLARE_API_TOKEN not found in environment or .env", file=sys.stderr)
        sys.exit(1)
    return token

def cf_request(endpoint: str, method: str = 'GET', data: dict = None) -> dict:
    token = get_token()
    url = f"https://api.cloudflare.com/client/v4{endpoint}"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, headers=headers, data=payload, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='ignore')
        print(f"Cloudflare API Error ({e.code}): {err_body}", file=sys.stderr)
        sys.exit(1)

def get_zone_id(zone_name: str = "milkcat.org") -> str:
    res = cf_request(f"/zones?name={zone_name}")
    zones = res.get('result', [])
    if not zones:
        print(f"Error: Zone {zone_name} not found.", file=sys.stderr)
        sys.exit(1)
    return zones[0]['id']

def list_records(zone_id: str):
    res = cf_request(f"/zones/{zone_id}/dns_records?per_page=100")
    records = res.get('result', [])
    print(f"\n📡 Cloudflare DNS Records for milkcat.org ({len(records)} records):")
    print(f"{'Type':<6} {'Name':<35} {'Content':<35} {'Proxied'}")
    print("-" * 85)
    for r in sorted(records, key=lambda x: (x.get('type'), x.get('name'))):
        print(f"{r.get('type'):<6} {r.get('name'):<35} {r.get('content'):<35} {r.get('proxied')}")

def set_record(zone_id: str, name: str, content: str, rtype: str = "A", proxied: bool = False):
    full_name = name if name.endswith("milkcat.org") else f"{name}.milkcat.org"
    res = cf_request(f"/zones/{zone_id}/dns_records?name={full_name}&type={rtype}")
    records = res.get('result', [])
    payload = {'type': rtype, 'name': full_name, 'content': content, 'proxied': proxied}
    if records:
        rec = records[0]
        rec_id = rec['id']
        cf_request(f"/zones/{zone_id}/dns_records/{rec_id}", method='PUT', data=payload)
        print(f"✅ Updated record: {full_name} ({rtype}) -> {content} (proxied={proxied})")
    else:
        cf_request(f"/zones/{zone_id}/dns_records", method='POST', data=payload)
        print(f"✅ Created record: {full_name} ({rtype}) -> {content} (proxied={proxied})")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="AgentOS Cloudflare DNS Manager")
    parser.add_argument('action', choices=['list', 'set', 'zone-status'])
    parser.add_argument('--name', help="Subdomain name (e.g. agentos, idiotfrog)")
    parser.add_argument('--ip', default="161.33.24.170", help="Target IP or CNAME destination")
    parser.add_argument('--type', default="A", choices=['A', 'CNAME', 'TXT'], help="DNS Record Type (default: A)")
    parser.add_argument('--proxied', action='store_true', help="Enable Cloudflare proxy")
    args = parser.parse_args()

    zone_id = get_zone_id()
    if args.action == 'list':
        list_records(zone_id)
    elif args.action == 'zone-status':
        res = cf_request(f"/zones/{zone_id}")
        z = res.get('result', {})
        print(f"Zone: {z.get('name')} | Status: {z.get('status')} | Nameservers: {z.get('name_servers')}")
    elif args.action == 'set':
        if not args.name:
            print("Error: --name is required for set action", file=sys.stderr)
            sys.exit(1)
        set_record(zone_id, args.name, args.ip, args.type, args.proxied)
