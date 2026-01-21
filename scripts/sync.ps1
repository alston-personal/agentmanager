# Sync AI Command Center to Git
$ErrorActionPreference = "Stop"

Write-Host "Starting Sync..." -ForegroundColor Cyan

# Add all changes
git add .

# Commit
$date = Get-Date -Format "yyyy-MM-dd HH:mm"
try {
    git commit -m "Auto update: $date"
    Write-Host "Committed changes." -ForegroundColor Green
}
catch {
    Write-Host "Nothing to commit." -ForegroundColor Yellow
}

# Push
git push

Write-Host "Sync Complete." -ForegroundColor Cyan
