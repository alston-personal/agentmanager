import requests
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
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"Error fetching repos: {r.status_code} - {r.text}")
        return []
    repos.extend(r.json())
    while 'next' in r.links:
        r = requests.get(r.links['next']['url'], headers=HEADERS)
        repos.extend(r.json())
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
        org_repo = org_repo_names[name_lower]
        if repo['updated_at'] > org_repo['updated_at']:
            # 個人版比較新，自動納入遷移 (覆蓋策略)
            transfer_list.append(name)
        else:
            skip_list.append(f"⏩ {name} (組織版已是最新)")
    else:
        transfer_list.append(name)

if not transfer_list:
    print("沒有需要遷移的倉庫。")
    sys.exit()

print(f"\n--- 準備遷移 {len(transfer_list)} 個倉庫 ---")
for name in transfer_list:
    print(f"🚀 正在遷移 {name}...")
    url = f"https://api.github.com/repos/{SOURCE_USER}/{name}/transfer"
    data = {"new_owner": TARGET_ORG}
    r = requests.post(url, headers=HEADERS, json={"new_owner": TARGET_ORG})
    if r.status_code in [202, 201]:
        print(f"✅ {name} 遷移請求已發送。")
    else:
        print(f"❌ {name} 遷移失敗: {r.status_code} - {r.text}")

print("\n--- 跳過清單 ---")
for item in skip_list:
    print(item)
