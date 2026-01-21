param (
  [Parameter(Mandatory = $true)]
  [string]$Name
)

$RootPath = Resolve-Path "$PSScriptRoot\.."
$ProjectDir = Join-Path "$RootPath\projects" $Name

# 1. 檢查是否已存在
if (Test-Path $ProjectDir) {
  Write-Host "⚠️  Project '$Name' already exists!" -ForegroundColor Yellow
  exit
}

# 2. 建立標準目錄結構
Write-Host "Creating project structure for '$Name'..." -ForegroundColor Cyan
New-Item -Path $ProjectDir -ItemType Directory -Force | Out-Null
New-Item -Path "$ProjectDir\notebooks" -ItemType Directory -Force | Out-Null
New-Item -Path "$ProjectDir\data" -ItemType Directory -Force | Out-Null
New-Item -Path "$ProjectDir\src" -ItemType Directory -Force | Out-Null

# 3. 建立 README
$ReadmeContent = @"
# $Name

## 🎯 Objective
Description of the project...

## 📂 Structure
- **notebooks/**: Jupyter notebooks
- **data/**: Datasets (add to .gitignore if large)
- **src/**: Source code
"@
Set-Content -Path "$ProjectDir\README.md" -Value $ReadmeContent

# 4. 提示更新 Dashboard
$DashboardLine = "| [$Name](./projects/$Name) | 🆕 Created | Setup Environment |"

Write-Host "✅ Project created successfully at: $ProjectDir" -ForegroundColor Green
Write-Host "`n📝 [ACTION REQUIRED] Copy this line to your DASHBOARD.md table:" -ForegroundColor Yellow
Write-Host $DashboardLine -ForegroundColor White
Write-Host "`n"
