# synop-fill: ตัวควบคุมการเปิด/ปิดระบบบน Windows (ไฟล์ .bat ใน script/ เรียกไฟล์นี้อีกที)
# ใช้:  powershell -NoProfile -ExecutionPolicy Bypass -File script\app.ps1 <action> [-NoBrowser] [-NoDialog]
#   start            รันระบบเบื้องหลังด้วย Python venv แล้วเปิดเบราว์เซอร์ (ถ้ารันอยู่แล้วแค่เปิดเบราว์เซอร์)
#   stop             หยุดระบบที่รันเบื้องหลัง
#   status           ดูว่ากำลังรันอยู่หรือไม่
#   autostart        ให้ระบบขึ้นเองเมื่อเข้า Windows (shortcut ใน Startup ไม่ต้องใช้สิทธิ์ admin)
#   autostart-remove เลิกให้ขึ้นเอง
#   docker-start     เปิดระบบด้วย Docker (โหมดเสริม)
#   docker-stop      หยุด container
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('start', 'stop', 'status', 'autostart', 'autostart-remove', 'docker-start', 'docker-stop')]
  [string]$Action,
  [switch]$NoBrowser,   # ไม่เปิดเบราว์เซอร์ (ใช้ตอนทดสอบ)
  [switch]$NoDialog     # พิมพ์ข้อความลงหน้าจอแทนหน้าต่างแจ้งเตือน (ใช้ตอนทดสอบ)
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$RunDir = Join-Path $Root '.run'
$LogDir = Join-Path $Root 'logs'
$PidFile = Join-Path $RunDir 'app.pid'
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
if ($env:SYNOP_NO_BROWSER -eq '1') { $NoBrowser = $true }
if ($env:SYNOP_NO_DIALOG -eq '1') { $NoDialog = $true }

function Show-Message([string]$Text, [string]$Kind = 'Information') {
  Write-Host $Text
  if ($NoDialog) { return }
  try {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($Text, 'ระบบกรอกรายงานผลการตรวจอากาศ', 'OK', $Kind)
  } catch { }
}
function Fail([string]$Text) { Show-Message $Text 'Warning'; exit 1 }

function Read-Settings {
  $envFile = Join-Path $Root '.env'
  if (-not (Test-Path $envFile)) {
    $example = Join-Path $Root '.env.example'
    if (Test-Path $example) { Copy-Item $example $envFile }
  }
  $s = @{ SYNOP_PORT = '8765'; SYNOP_BIND = '127.0.0.1' }
  if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile -Encoding UTF8) {
      if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$' -and -not $line.TrimStart().StartsWith('#')) { $s[$Matches[1]] = $Matches[2] }
    }
  }
  $port = 0
  if (-not [int]::TryParse($s['SYNOP_PORT'], [ref]$port) -or $port -lt 1024 -or $port -gt 65535) {
    Fail ("ค่า SYNOP_PORT ในไฟล์ .env ไม่ถูกต้อง (" + $s['SYNOP_PORT'] + ")`nต้องเป็นตัวเลข 1024 ถึง 65535 เช่น 8765")
  }
  if ($s['SYNOP_BIND'] -notmatch '^[0-9A-Fa-f:.]+$') {
    Fail ("ค่า SYNOP_BIND ในไฟล์ .env ไม่ถูกต้อง (" + $s['SYNOP_BIND'] + ")`nใส่ 127.0.0.1 (เปิดได้เฉพาะเครื่องนี้) หรือ 0.0.0.0 (เครื่องอื่นในเครือข่ายเข้าได้)")
  }
  return @{ Port = $port; Bind = $s['SYNOP_BIND'] }
}

function Test-OurApp([int]$Port) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
    return (($r.Content | ConvertFrom-Json).app -eq 'synop-fill')
  } catch { return $false }
}
function Test-PortBusy([int]$Port) {
  try { return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop) } catch { return $false }
}
function Open-Browser([int]$Port) { if (-not $NoBrowser) { Start-Process "http://localhost:$Port/" } }

function Find-Python {
  # ต้องเป็น Python 3.12 ขึ้นไป (ลอง py launcher ก่อน แล้วค่อย python)
  $candidates = @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3'), @('python'))
  foreach ($c in $candidates) {
    try {
      $exe = $c[0]; $args2 = @(); if ($c.Count -gt 1) { $args2 = $c[1..($c.Count - 1)] }
      $ok = & $exe @args2 -c "import sys;print(1 if sys.version_info>=(3,12) else 0)" 2>$null
      if ($LASTEXITCODE -eq 0 -and "$ok".Trim() -eq '1') { return ,@($exe) + $args2 }
    } catch { }
  }
  return $null
}
function Test-Venv {
  if (-not (Test-Path $VenvPython)) { return $false }
  try { & $VenvPython -c "import fastapi, uvicorn, multipart" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
function Ensure-Venv {
  if (Test-Venv) { return }
  $py = Find-Python
  if (-not $py) {
    Fail "ไม่พบ Python เวอร์ชัน 3.12 ขึ้นไปในเครื่องนี้`n`nวิธีแก้: ติดตั้ง Python จาก python.org แล้วติ๊ก 'Add python.exe to PATH' ตอนติดตั้ง จากนั้นเปิดโปรแกรมนี้ใหม่"
  }
  Write-Host 'กำลังติดตั้งระบบครั้งแรก ใช้เวลาสักครู่ กรุณาอย่าปิดหน้าต่างนี้ ...'
  if (Test-Path (Join-Path $Root '.venv')) { Remove-Item (Join-Path $Root '.venv') -Recurse -Force }
  $exe = $py[0]; $a = @(); if ($py.Count -gt 1) { $a = $py[1..($py.Count - 1)] }
  & $exe @a -m venv (Join-Path $Root '.venv')
  if ($LASTEXITCODE -ne 0) { Fail 'สร้างสภาพแวดล้อม Python (.venv) ไม่สำเร็จ' }
  $wheels = Join-Path $Root 'vendor\wheels'
  $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $Root 'requirements.txt'))
  if (Test-Path $wheels) { $pipArgs += @('--no-index', '--find-links', $wheels) }
  & $VenvPython @pipArgs
  if ($LASTEXITCODE -ne 0) {
    Fail "ติดตั้งโปรแกรมที่ต้องใช้ไม่สำเร็จ`n`nถ้าเครื่องนี้ไม่ได้ต่ออินเทอร์เน็ต ให้วางไฟล์ติดตั้งไว้ในโฟลเดอร์ vendor\wheels แล้วเปิดใหม่"
  }
}

function Get-SavedPid {
  if (-not (Test-Path $PidFile)) { return $null }
  $p = 0
  if ([int]::TryParse((Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1), [ref]$p)) { return $p }
  return $null
}
function Get-AppProcesses {
  # โปรเซส uvicorn ของโฟลเดอร์นี้ (กันกรณีไฟล์ PID หายหรือค้าง)
  Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*uvicorn*app.main:app*' -and $_.ExecutablePath -like "$Root*" }
}

function Start-App {
  $cfg = Read-Settings
  $port = $cfg.Port
  if (Test-OurApp $port) { Open-Browser $port; Write-Host "ระบบทำงานอยู่แล้วที่ http://localhost:$port/"; return }
  if (Test-PortBusy $port) {
    Fail ("พอร์ต $port ถูกโปรแกรมอื่นใช้งานอยู่ เปิดระบบไม่ได้`n`nวิธีแก้: เปิดไฟล์ .env ในโฟลเดอร์โปรแกรม แล้วเปลี่ยนเลข SYNOP_PORT เป็นเลขอื่น เช่น 8766 จากนั้นเปิดใหม่")
  }
  Ensure-Venv
  New-Item -ItemType Directory -Force $RunDir, $LogDir | Out-Null
  $log = Join-Path $LogDir 'app.log'; $err = Join-Path $LogDir 'app.err.log'
  foreach ($f in @($log, $err)) {  # กันไฟล์ log โตไม่สิ้นสุด
    if ((Test-Path $f) -and ((Get-Item $f).Length -gt 5MB)) { Move-Item $f "$f.1" -Force }
  }
  # ให้ cmd เป็นคนเขียน log (ใช้ path แบบสัมพัทธ์ ไม่ให้ชื่อโฟลเดอร์ภาษาไทยปนในคำสั่ง) และเปิดแบบไม่สืบทอด handle
  # ของผู้เรียก ไม่เช่นนั้นโปรแกรมที่เรียกสคริปต์แล้วรอรับผลลัพธ์จะค้างจนกว่าระบบจะปิด
  $cmdArgs = '/c ".venv\Scripts\python.exe -m uvicorn app.main:app --host ' + $cfg.Bind + ' --port ' + $port + ' >> logs\app.log 2>> logs\app.err.log"'
  $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdArgs -WorkingDirectory $Root -WindowStyle Hidden -PassThru
  Set-Content -Path $PidFile -Value $proc.Id
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-OurApp $port) { Open-Browser $port; Write-Host "เปิดระบบแล้วที่ http://localhost:$port/"; return }
    if ($proc.HasExited) { break }
  }
  $tail = ''
  if (Test-Path $err) { $tail = (Get-Content $err -Tail 6 -ErrorAction SilentlyContinue) -join "`n" }
  if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
  Remove-Item $PidFile -ErrorAction SilentlyContinue
  Fail ("เปิดระบบไม่สำเร็จ`nดูรายละเอียดในไฟล์ logs\app.err.log`n`n" + $tail)
}

function Stop-Tree([int]$ProcessId) {
  # venv ของ Windows เปิด python ตัวจริงเป็นโปรเซสลูก จึงฆ่าทั้งต้นไม้ (/T) ไม่ให้มีตัวค้างจองพอร์ต
  & taskkill /PID $ProcessId /T /F 2>$null | Out-Null
}
function Stop-App {
  $stopped = 0
  $saved = Get-SavedPid
  if ($saved -and (Get-Process -Id $saved -ErrorAction SilentlyContinue)) { Stop-Tree $saved; $stopped++ }
  foreach ($p in @(Get-AppProcesses)) { Stop-Tree $p.ProcessId; $stopped++ }
  # ทางสำรอง: ถ้าพอร์ตของเรายังตอบอยู่ ฆ่าโปรเซสที่ถือพอร์ตนั้น (เฉพาะเมื่อเป็นระบบของเราจริง)
  $cfg = Read-Settings
  if (Test-OurApp $cfg.Port) {
    foreach ($c in @(Get-NetTCPConnection -LocalPort $cfg.Port -State Listen -ErrorAction SilentlyContinue)) {
      Stop-Tree $c.OwningProcess; $stopped++
    }
  }
  Remove-Item $PidFile -ErrorAction SilentlyContinue
  if ($stopped -gt 0) { Show-Message 'หยุดระบบแล้ว' } else { Show-Message 'ระบบไม่ได้ทำงานอยู่' }
}

function Show-Status {
  $cfg = Read-Settings
  if (Test-OurApp $cfg.Port) { Write-Host ("ทำงานอยู่ที่ http://localhost:" + $cfg.Port + "/") }
  else { Write-Host 'ไม่ได้ทำงาน' }
}

function Get-StartupLink { Join-Path ([Environment]::GetFolderPath('Startup')) 'synop-fill.lnk' }
function Set-Autostart {
  $shell = New-Object -ComObject WScript.Shell
  $lnk = $shell.CreateShortcut((Get-StartupLink))
  $lnk.TargetPath = Join-Path $Root 'script\run-app.bat'
  $lnk.Arguments = '-NoBrowser'
  $lnk.WorkingDirectory = $Root
  $lnk.WindowStyle = 7  # ย่อหน้าต่าง
  $lnk.Description = 'synop-fill: เปิดระบบกรอกรายงานผลการตรวจอากาศเบื้องหลัง'
  $lnk.Save()
  Show-Message "ตั้งให้ระบบเปิดเองเมื่อเข้า Windows แล้ว`n(ถ้าเครื่องรีสตาร์ตเองแล้วไม่มีคนเข้าระบบ Windows ระบบจะยังไม่ขึ้น)"
}
function Remove-Autostart {
  $l = Get-StartupLink
  if (Test-Path $l) { Remove-Item $l -Force; Show-Message 'เลิกให้ระบบเปิดเองแล้ว' } else { Show-Message 'ยังไม่ได้ตั้งให้เปิดเอง' }
}

# ------------------------------ โหมด Docker (เสริม) ------------------------------
function Test-DockerReady { try { & docker info 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false } }
function Start-Docker {
  $cfg = Read-Settings; $port = $cfg.Port
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "ไม่พบ Docker ในเครื่องนี้`nถ้าไม่ได้ใช้ Docker ให้เปิดด้วยไฟล์ run-app.bat แทน" }
  if (-not (Test-DockerReady)) {
    $dd = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dd) { Write-Host 'กำลังเปิด Docker Desktop รอสักครู่ ...'; Start-Process $dd }
    for ($i = 0; $i -lt 60 -and -not (Test-DockerReady); $i++) { Start-Sleep -Seconds 2 }
    if (-not (Test-DockerReady)) { Fail 'Docker ยังไม่พร้อมใช้งาน กรุณาเปิดโปรแกรม Docker Desktop ให้ขึ้นสถานะพร้อมก่อน แล้วลองใหม่' }
  }
  if (Test-OurApp $port) { Open-Browser $port; Write-Host "ระบบทำงานอยู่แล้วที่ http://localhost:$port/"; return }
  if (Test-PortBusy $port) {
    Fail ("พอร์ต $port ถูกโปรแกรมอื่นใช้งานอยู่ เปิดระบบไม่ได้`n`nวิธีแก้: เปิดไฟล์ .env แล้วเปลี่ยนเลข SYNOP_PORT เป็นเลขอื่น เช่น 8766 จากนั้นเปิดใหม่")
  }
  & docker compose up -d --build
  if ($LASTEXITCODE -ne 0) { Fail 'เปิด container ไม่สำเร็จ ดูข้อความผิดพลาดด้านบนหรือแจ้งผู้ดูแล' }
  for ($i = 0; $i -lt 60; $i++) {
    if (Test-OurApp $port) { Open-Browser $port; Write-Host "เปิดระบบแล้วที่ http://localhost:$port/"; return }
    Start-Sleep -Seconds 1
  }
  Fail 'container เปิดแล้วแต่ระบบยังไม่ตอบสนอง ดู log ด้วยคำสั่ง docker compose logs'
}
function Stop-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'ไม่พบ Docker ในเครื่องนี้' }
  & docker compose stop
  Show-Message 'หยุด container แล้ว'
}

switch ($Action) {
  'start' { Start-App }
  'stop' { Stop-App }
  'status' { Show-Status }
  'autostart' { Set-Autostart }
  'autostart-remove' { Remove-Autostart }
  'docker-start' { Start-Docker }
  'docker-stop' { Stop-Docker }
}
