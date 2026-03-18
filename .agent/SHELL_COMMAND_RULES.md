# 🖥️ Shell 指令規則

## ⚠️ 重要：Antigravity AI 只使用 Git Bash 語法

**此規則適用於這個 workspace 的所有 AI 操作。**

---

## 🎯 核心規則

### Windows 環境下永遠使用 Git Bash / Unix 語法

當 Antigravity AI 需要執行 shell 指令時：
- ✅ **使用 Git Bash / Unix 語法**
- ❌ **不要使用 PowerShell 語法**
- ✅ 假設 Git for Windows 已安裝（包含 Git Bash）
- ✅ 路徑使用 Unix 風格

---

## ✅ 允許的指令（Git Bash / Unix）

### 檔案操作
```bash
# 複製
cp source dest              # 單一檔案
cp -r source dest           # 遞迴複製目錄

# 移動/重命名
mv source dest

# 刪除
rm file                     # 刪除檔案
rm -rf directory            # 遞迴刪除目錄

# 創建目錄
mkdir dirname               # 單層目錄
mkdir -p path/to/dir        # 遞迴創建

# 列出檔案
ls                          # 基本列出
ls -la                      # 詳細列出（包含隱藏檔）
ls -R                       # 遞迴列出

# 查看檔案
cat file                    # 顯示全部內容
head -n 20 file             # 顯示前 20 行
tail -n 20 file             # 顯示後 20 行
```

### 路徑表示
```bash
# Windows 路徑轉換
cd /d/AgentManager          # ✅ D:\AgentManager
cd /c/Users/name            # ✅ C:\Users\name

# Unix 風格路徑
cd ~/workspace              # 使用者主目錄
cd ../..                    # 相對路徑
pwd                         # 顯示當前目錄
```

### Git 操作
```bash
git clone URL
git add .
git add file
git commit -m "message"
git push origin main
git pull
git status
git log --oneline -5
```

### 其他常用指令
```bash
# 搜尋
grep "pattern" file
find . -name "*.py"

# 文字處理
echo "text" > file          # 覆寫
echo "text" >> file         # 附加
sed 's/old/new/g' file

# 權限（macOS/Linux）
chmod +x script.sh

# 查看環境
which python
env | grep GITHUB
```

---

## ❌ 禁止的指令（PowerShell 專有）

### 不要使用這些 PowerShell Cmdlet

```powershell
# ❌ 檔案操作
Copy-Item                   # 用 cp 代替
Copy-Item -Recurse          # 用 cp -r 代替
Remove-Item                 # 用 rm 代替
Remove-Item -Recurse -Force # 用 rm -rf 代替
Move-Item                   # 用 mv 代替
New-Item -ItemType File     # 用 touch 代替
New-Item -ItemType Directory # 用 mkdir 代替

# ❌ 列出檔案
Get-ChildItem               # 用 ls 代替
Get-ChildItem -Recurse      # 用 ls -R 或 find 代替
dir                         # 用 ls 代替

# ❌ 其他
Get-Content                 # 用 cat 代替
Set-Content                 # 用 echo > 代替
Write-Host                  # 用 echo 代替
```

---

## 📋 完整對照表

| ❌ PowerShell | ✅ Git Bash | 說明 |
|--------------|------------|------|
| `Copy-Item src dst` | `cp src dst` | 複製檔案 |
| `Copy-Item -Recurse src dst` | `cp -r src dst` | 複製目錄 |
| `Copy-Item -Force` | `cp -f` | 強制覆蓋 |
| `Remove-Item file` | `rm file` | 刪除檔案 |
| `Remove-Item -Recurse -Force dir` | `rm -rf dir` | 刪除目錄 |
| `Move-Item src dst` | `mv src dst` | 移動/重命名 |
| `New-Item -ItemType Directory` | `mkdir -p` | 創建目錄 |
| `Get-ChildItem` | `ls` | 列出檔案 |
| `Get-ChildItem -Recurse` | `ls -R` 或 `find .` | 遞迴列出 |
| `Get-Content file` | `cat file` | 查看檔案 |
| `Set-Content` | `echo "text" > file` | 寫入檔案 |
| `Write-Host "text"` | `echo "text"` | 輸出文字 |
| `Test-Path` | `[ -e path ]` 或 `ls path` | 檢查路徑 |

---

## 🎯 實際應用範例

### 範例 1：複製 skills 到新位置

❌ **錯誤（PowerShell）**
```powershell
Copy-Item -Recurse d:\AgentManager\.agent\skills d:\NewWorkspace\.agent\skills
```

✅ **正確（Git Bash）**
```bash
cp -r /d/AgentManager/.agent/skills /d/NewWorkspace/.agent/skills
```

### 範例 2：刪除並重新創建目錄

❌ **錯誤（PowerShell）**
```powershell
Remove-Item -Recurse -Force .\temp
New-Item -ItemType Directory -Path .\temp
```

✅ **正確（Git Bash）**
```bash
rm -rf ./temp
mkdir -p ./temp
```

### 範例 3：查看檔案並複製

❌ **錯誤（PowerShell）**
```powershell
Get-ChildItem | Where-Object {$_.Extension -eq ".md"}
Copy-Item *.md ../backup/
```

✅ **正確（Git Bash）**
```bash
ls *.md
cp *.md ../backup/
```

---

## 🔧 執行工具選擇

### run_command 工具
當使用 `run_command` 工具時：
- ✅ `CommandLine` 使用 Git Bash 語法
- ✅ 路徑使用 Unix 風格（`/d/path`）
- ❌ 不使用 PowerShell 特有參數

### 範例
```json
{
  "CommandLine": "cp -r /d/AgentManager/.agent/skills /d/NewWorkspace/.agent/",
  "Cwd": "/d/NewWorkspace",
  "SafeToAutoRun": false
}
```

---

## 💡 為什麼只用 Git Bash？

### 優點
1. ✅ **跨平台一致** - Windows/macOS/Linux 使用相同語法
2. ✅ **學習成本低** - 只需學一套指令
3. ✅ **文檔統一** - 所有範例都能直接使用
4. ✅ **簡潔清晰** - Unix 指令通常更短
5. ✅ **社群標準** - 大部分文檔和教學都用 Unix 語法

### Git Bash 的可用性
- ✅ Git for Windows 包含完整的 Git Bash
- ✅ 支援所有常用 Unix 工具
- ✅ 支援 bash 腳本
- ✅ Windows 用戶普遍已安裝

---

## 🚫 執行檢查清單

在執行任何指令前，Antigravity AI 應確認：
- [ ] 是否使用 Unix/Bash 語法？
- [ ] 路徑是否使用 Unix 風格（`/d/` 而非 `D:\`）？
- [ ] 沒有使用 PowerShell Cmdlet（如 `Copy-Item`, `Get-ChildItem`）？
- [ ] 指令是否可以在 Git Bash 中執行？

---

## 📚 參考資源

- [Git Bash 基礎](https://git-scm.com/docs)
- [Bash 指令參考](https://www.gnu.org/software/bash/manual/)
- [Unix 指令教學](https://www.shellscript.sh/)

---

**⚠️ 此規則對 Antigravity AI 是強制性的。所有 shell 指令都必須使用 Git Bash 語法。**

---

## 🔗 其他重要規則
請務必同時閱讀並遵守 [Agent Rules](AGENT_RULES.md) 中的執行規範。
