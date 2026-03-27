param (
  [Parameter(Mandatory = $true)]
  [string]$SourcePath
)

# 正規化路徑
$SourceItem = Get-Item $SourcePath
$ProjectName = $SourceItem.Name
$RootPath = Resolve-Path "$PSScriptRoot\.."
$DestPath = Join-Path "$RootPath\projects" $ProjectName

# 1. 檢查來源
if (-not (Test-Path $SourcePath)) {
  Write-Host "❌ Error: Source path '$SourcePath' does not exist." -ForegroundColor Red
  exit
}

# 2. 檢查目標是否已有同名專案
if (Test-Path $DestPath) {
  Write-Host "⚠️  Warning: A project named '$ProjectName' already exists in projects/." -ForegroundColor Yellow
  exit
}

# 3. 執行移動
Write-Host "Moving '$ProjectName' into Command Center..." -ForegroundColor Cyan
Move-Item -Path $SourcePath -Destination $DestPath

# 4. 檢測是否為 Git Repo
if (Test-Path "$DestPath\.git") {
  Write-Host "ℹ️  Note: The imported project is a Git repository." -ForegroundColor Gray
  Write-Host "    It will behave as a 'nested repository' (Command Center won't track its files, only the folder)." -ForegroundColor Gray
}

# 5. 完成提示
$DashboardLine = "| [$ProjectName](./projects/$ProjectName) | 📥 Imported | Review Status |"
Write-Host "✅ Project imported successfully!" -ForegroundColor Green
Write-Host "`n📝 [ACTION REQUIRED] Add this to DASHBOARD.md:" -ForegroundColor Yellow
Write-Host $DashboardLine -ForegroundColor White
Write-Host "`n"
