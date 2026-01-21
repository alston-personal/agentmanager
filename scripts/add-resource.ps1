param (
  [string]$Type,
  [string]$Name,
  [string]$Link
)

# Define Emojis using safe ASCII character codes to avoid encoding errors in the script file
# Cloud (2601)
$IconCloud = [char]0x2601 
# Chat (1F4AC -> D83D DCAC)
$IconChat = "$([char]0xD83D)$([char]0xDCAC)"
# Desktop (1F5A5 -> D83D DDA5)
$IconDesktop = "$([char]0xD83D)$([char]0xDDA5)"
# Satellite (1F4E1 -> D83D DCE1)
$IconSat = "$([char]0xD83D)$([char]0xDCE1)"

# 1. Ask for Type if missing
if (-not $Type) {
  Write-Host "Select Resource Type:" -ForegroundColor Cyan
  Write-Host "1. $IconCloud  Colab"
  Write-Host "2. $IconChat  ChatGPT/AI Chat"
  Write-Host "3. $IconDesktop  Local Project"
  Write-Host "4. $IconSat  Web Resource"
  $Selection = Read-Host "Choice (1-4)"
    
  switch ($Selection) {
    "1" { $Type = $IconCloud; $LinkType = "Note" }
    "2" { $Type = $IconChat; $LinkType = "Chat" }
    "3" { $Type = $IconDesktop; $LinkType = "Folder" }
    "4" { $Type = $IconSat; $LinkType = "Link" }
    Default { $Type = "?"; $LinkType = "Link" }
  }
}

# 2. Ask for Name if missing
if (-not $Name) {
  $Name = Read-Host "Project/Resource Name"
}

# 3. Ask for Link if missing
if (-not $Link) {
  $Link = Read-Host "Link / URL"
}

# Construct the Markdown row safely
# Format: | Type | Name | Link | Status |
$NewRow = "| $Type | **$Name** | [$LinkType]($Link) | Active |"

# Path to Dashboard
$DashboardPath = "$PSScriptRoot\..\DASHBOARD.md"

# Read content
$Content = Get-Content $DashboardPath -Encoding UTF8

# Find where to insert (Active Projects table)
$TableStartIndex = 0
for ($i = 0; $i -lt $Content.Count; $i++) {
  # Look for the header row
  if ($Content[$i] -match "\| Type \| Project") {
    # Check if the next line is the separator line
    if ($i + 1 -lt $Content.Count -and $Content[$i + 1] -match "\| :---") {
      $TableStartIndex = $i + 2
      break
    }
  }
}

if ($TableStartIndex -gt 0) {
  $NewContent = @()
  # Add top part
  $NewContent += $Content[0..($TableStartIndex - 1)]
  # Add new row
  $NewContent += $NewRow
  # Add bottom part
  if ($TableStartIndex -lt $Content.Count) {
    $NewContent += $Content[$TableStartIndex..($Content.Count - 1)]
  }
    
  # Write back
  $NewContent | Set-Content $DashboardPath -Encoding UTF8
    
  Write-Host "Success! Added to Dashboard:" -ForegroundColor Green
  Write-Host $NewRow -ForegroundColor Gray
}
else {
  Write-Host "Error: Could not find the target table in DASHBOARD.md" -ForegroundColor Red
  Write-Host "Please ensure DASHBOARD.md has a table with '| Type | Project' header."
}
