param(
  [string]$ProfileUrl = 'https://www.threads.com/@oursong_alstonhuang',
  [string]$PostPrefix = '第三輪 AgentOS GUI Benchmark'
)
$ErrorActionPreference='Stop'
$sw=[Diagnostics.Stopwatch]::StartNew()
$marks=[ordered]@{}
function Mark([string]$n){$marks[$n]=[math]::Round($sw.Elapsed.TotalSeconds,2)}
function Stage([string]$s){
  $p=Join-Path $env:USERPROFILE 'AgentOS\agentos-demo\agentos-demo-state.json'
  if(Test-Path $p){
    try{
      $d=Get-Content -Raw -LiteralPath $p | ConvertFrom-Json
      $d.stage=$s
      $t=$p+'.tmp'
      $d | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $t -Encoding UTF8
      Move-Item -Force -LiteralPath $t -Destination $p
    }catch{}
  }
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class AOSW32 {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd,int n);
}
"@
function Edge(){
  $p=Get-Process msedge -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1
  if($null -eq $p){throw 'No visible Edge'}
  [AOSW32]::ShowWindow($p.MainWindowHandle,9)|Out-Null
  [AOSW32]::SetForegroundWindow($p.MainWindowHandle)|Out-Null
  $p
}
function AllUI($e){
  $r=[System.Windows.Automation.AutomationElement]::FromHandle($e.MainWindowHandle)
  $r.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
}
function Nav($e,[string]$url){
  [AOSW32]::SetForegroundWindow($e.MainWindowHandle)|Out-Null
  [System.Windows.Forms.SendKeys]::SendWait('^l')
  Set-Clipboard -Value $url
  [System.Windows.Forms.SendKeys]::SendWait('^v')
  [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}
$downloads=Join-Path $env:USERPROFILE 'Downloads'
$before=@{}
Get-ChildItem -LiteralPath $downloads -File -ErrorAction SilentlyContinue |
 Where-Object {$_.Extension -match '(?i)^\.(png|jpg|jpeg|webp)$'} |
 ForEach-Object {try{$before[(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash]=$_.FullName}catch{}}
$started=Get-Date
Mark 'benchmark_start'
$edge=Edge
Stage 'Gemini / opening'
Nav $edge 'https://gemini.google.com/app'
Start-Sleep -Seconds 4
Mark 'gemini_open'
$ui=AllUI $edge
$edit=$null
for($i=0;$i -lt $ui.Count;$i++){
  $x=$ui.Item($i)
  if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit){
    $r=$x.Current.BoundingRectangle
    if(-not [double]::IsInfinity($r.Y) -and $r.Y -gt 350 -and $r.Width -gt 300){$edit=$x;break}
  }
}
if($null -eq $edit){throw 'Gemini editor missing'}
$edit.SetFocus()
Set-Clipboard -Value '這是 AgentOS 第三輪 zero-rediscovery benchmark。請直接生成一張全新的 Threads 單張配圖：主題是 ChatGPT 與 Gemini 接力工作，從討論、生成素材到實際操作電腦發佈。溫暖電影感科技工作桌，兩個抽象 AI 光點彼此交接任務；不要大段文字、不要企業簡報風。請直接生成圖片，不要只描述。'
[System.Windows.Forms.SendKeys]::SendWait('^a')
[System.Windows.Forms.SendKeys]::SendWait('^v')
$ui=AllUI $edge
$send=$null
for($i=0;$i -lt $ui.Count;$i++){
  $x=$ui.Item($i)
  if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and [string]$x.Current.Name -eq '傳送訊息'){$send=$x;break}
}
if($null -eq $send){throw 'Gemini send missing'}
$send.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Mark 'gemini_sent'
Stage 'Gemini / generating fresh image'
$dl=$null
for($a=0;$a -lt 45 -and $null -eq $dl;$a++){
  Start-Sleep -Seconds 2
  $ui=AllUI $edge
  for($i=0;$i -lt $ui.Count;$i++){
    $x=$ui.Item($i)
    if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and [string]$x.Current.Name -eq '下載原尺寸圖片'){$dl=$x;break}
  }
}
if($null -eq $dl){throw 'Gemini image timeout'}
Mark 'image_ready'
$dl.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Stage 'Gemini / proving fresh asset'
$img=$null
$hash=$null
for($a=0;$a -lt 30 -and $null -eq $img;$a++){
  Start-Sleep -Seconds 1
  $cs=Get-ChildItem -LiteralPath $downloads -File -ErrorAction SilentlyContinue |
    Where-Object {$_.Extension -match '(?i)^\.(png|jpg|jpeg|webp)$' -and $_.LastWriteTime -ge $started.AddSeconds(-2)} |
    Sort-Object LastWriteTime -Descending
  foreach($c in $cs){
    try{
      $h=(Get-FileHash -Algorithm SHA256 -LiteralPath $c.FullName).Hash
      if(-not $before.ContainsKey($h) -and $c.Length -gt 10000){
        $n=$c.Length
        Start-Sleep -Milliseconds 400
        $c.Refresh()
        if($c.Length -eq $n){$img=$c;$hash=$h;break}
      }
    }catch{}
  }
}
if($null -eq $img){throw 'Fresh asset proof failed'}
Mark 'fresh_asset_downloaded'
Stage 'Threads / composing'
Nav $edge $ProfileUrl
Start-Sleep -Seconds 5
Mark 'threads_open'
$ui=AllUI $edge
$entry=$null
for($i=0;$i -lt $ui.Count;$i++){
  $x=$ui.Item($i)
  if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and [string]$x.Current.Name -like '文字欄位空白*撰寫新貼文*'){$entry=$x;break}
}
if($null -eq $entry){throw 'Threads entry missing'}
$entry.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Start-Sleep -Seconds 2
$ui=AllUI $edge
$composer=$null
for($i=0;$i -lt $ui.Count;$i++){
  $x=$ui.Item($i)
  if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit){
    $r=$x.Current.BoundingRectangle
    if(-not [double]::IsInfinity($r.Y) -and $r.Y -gt 250 -and $r.Width -gt 250){$composer=$x;break}
  }
}
if($null -eq $composer){throw 'Threads editor missing'}
$composer.SetFocus()
$nl=[Environment]::NewLine
$post=$PostPrefix+'：這次從零開始重新請 Gemini 產一張新圖，不沿用上一輪素材。'+$nl+$nl+'ChatGPT → Gemini 產圖 → AgentOS 操作電腦 → Threads 發佈 → Profile 驗證。'+$nl+$nl+'這輪同時一鏡到底錄影並跑碼錶，測的是做過之後能不能真正變快。'
Set-Clipboard -Value $post
[System.Windows.Forms.SendKeys]::SendWait('^a')
[System.Windows.Forms.SendKeys]::SendWait('^v')
$b=[System.Drawing.Image]::FromFile($img.FullName)
try{
  [System.Windows.Forms.Clipboard]::SetImage($b)
  Start-Sleep -Milliseconds 300
  [System.Windows.Forms.SendKeys]::SendWait('^v')
}finally{$b.Dispose()}
Start-Sleep -Seconds 6
Mark 'threads_draft_ready'
$ui=AllUI $edge
$pub=$null
for($i=0;$i -lt $ui.Count;$i++){
  $x=$ui.Item($i)
  if($x.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and [string]$x.Current.Name -eq '發佈' -and $x.Current.IsEnabled){
    $r=$x.Current.BoundingRectangle
    if(-not [double]::IsInfinity($r.Y) -and $r.Y -gt 350){$pub=$x;break}
  }
}
if($null -eq $pub){throw 'Publish missing'}
Stage 'Threads / publishing'
$pub.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Mark 'publish_invoked'
Stage 'Threads / profile readback'
$verified=$false
for($a=0;$a -lt 10 -and -not $verified;$a++){
  Start-Sleep -Seconds 2
  Nav $edge $ProfileUrl
  Start-Sleep -Seconds 3
  $ui=AllUI $edge
  for($i=0;$i -lt $ui.Count;$i++){
    if(([string]$ui.Item($i).Current.Name) -like ('*'+$PostPrefix+'*')){$verified=$true;break}
  }
}
if(-not $verified){throw 'Profile readback failed'}
Mark 'profile_verified'
Stage 'Verified / benchmark PASS'
[pscustomobject]@{
  schema='agentos.gui-demo-benchmark/v1'
  ok=$true
  verified=$true
  elapsed_seconds=[math]::Round($sw.Elapsed.TotalSeconds,2)
  image_path=$img.FullName
  image_bytes=$img.Length
  image_mtime=$img.LastWriteTime.ToString('o')
  image_sha256=$hash
  fresh_asset=(-not $before.ContainsKey($hash))
  marks=$marks
}|ConvertTo-Json -Depth 6 -Compress
