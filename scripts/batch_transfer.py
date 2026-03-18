import requests
import json
import os
import sys

TOKEN = open("/home/ubuntu/agentmanager/.gh_token").read().strip()
SOURCE_USER = "alstonhuang"
TARGET_ORG = "alston-personal"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_repos(url):
    repos = []
    while url:
        response = requests.get(url, headers=HEADERS)
        repos.extend(response.json())
        url = response.links.get('next', {}).get('url')
    return repos

print(f"--- 正在檢索 {SOURCE_USER} 的倉庫 ---")
personal_repos = get_repos(f"https://api.github.com/users/{SOURCE_USER}/repos?per_page=100")
print(f"--- 正在檢索 {TARGET_ORG} 的倉庫 ---")
org_repos = get_repos(f"https://api.github.com/orgs/{TARGET_ORG}/repos?per_page=100")

org_repo_names = {r['name'].lower(): r for r in org_repos}

transfer_list = []
skip_list = []

for repo in personal_repos:
    name = repo['name']
    name_lower = name.lower()
    
    if name_lower in org_repo_names:
        # 如果組織已有，比較更新時間
        org_repo = org_repo_names[name_lower]
        if repo['updated_at'] > org_repo['updated_at']:
            # 個人版比較新，通常建議手動處理或警告
            skip_list.append(f"⚠️ {name} (組織已有，且個人版較新 [{repo['updated_at']} > {org_repo['updated_at']}])")
        else:
            skip_list.append(f"⏩ {name} (組織版已是最新)")
    else:
        transfer_list.append(name)

print("\n--- 待遷移待辦清單 ---")
for name in transfer_list:
    print(f"READY: {name}")

print("\n--- 跳過清單 ---")
for item in skip_list:
    print(item)

confirm = input("\n👉 是否執行以上 READY 的遷移？ (y/n): ")
if confirm.lower() != 'y':
    print("已取消。")
    sys.exit()

for name in transfer_list:
    print(f"🚀 正在遷移 {name}...")
    url = f"https://api.github.com/repos/{SOURCE_USER}/{name}/transfer"
    data = {"new_owner": TARGET_ORG}
    response = requests.post(url, headers=HEADERS, json=data)
    if response.status_code == 202:
        print(f"✅ {name} 遷移請求已發送 (請查收確認信)。")
    else:
        print(f"❌ {name} 遷移失敗: {response.status_code} - {response.text}")

