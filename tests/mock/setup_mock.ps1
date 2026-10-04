param()
# ============================================================
#  MaaAutoBoot Mock test env builder
#  Creates fake MAA / MAAEnd targets (renamed cmd.exe copies)
#  and a portable config.json so EVERYTHING runs in this folder.
#  No game, no emulator, no real MAA needed. 1-core / 1GB VM is enough.
# ============================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Write-Host "=== MaaAutoBoot Mock test env ===" -ForegroundColor Cyan
Write-Host "folder: $root"

# --- 1. main program must be here (portable mode) ---
$exe = Join-Path $root "MaaAutoBoot.exe"
if (-not (Test-Path $exe)) {
    Write-Host ""
    Write-Host "[X] MaaAutoBoot.exe not found in this folder." -ForegroundColor Red
    Write-Host "    Copy MaaAutoBoot.exe here first, then run setup_mock.cmd again."
    exit 1
}
Write-Host "[OK] MaaAutoBoot.exe found"

# --- 2. fake targets: renamed cmd.exe (monitored name = MAAEnd.exe / MAA.exe) ---
foreach ($name in @("MAAEnd.exe", "MAA.exe")) {
    $dst = Join-Path $root $name
    try {
        Copy-Item "$env:SystemRoot\System32\cmd.exe" $dst -Force
        Write-Host "[OK] $name  <- cmd.exe copy (fake assistant process)"
    } catch {
        Write-Host "[X] cannot create $name (is it running? close it first): $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# --- 3. portable config.json: gate always-open, success->shutdown, failure->keep ---
$cfg = [ordered]@{
    version = 1
    gate = @{ enabled = $true; start = "00:00"; end = "23:59" }   # logic still runs, window = all day
    emulator = @{ enabled = $false; ldconsole_path = ""; index = 0; package = ""; launch_wait_sec = 60 }
    shutdown = @{ enabled = $true; grace_sec = 15; on_failure = "keep" }   # failure keeps machine on
    maaend = @{
        enabled = $true
        path = (Join-Path $root "MAAEnd.exe")
        args = "/c mock_maaend.cmd"          # cwd = exe dir -> relative is fine
        start_mode = "cli"
        timeout_min = 10
        close_after = $true
        kill_names = @("MAAEnd.exe")
    }
    maa = @{
        enabled = $true
        path = (Join-Path $root "MAA.exe")
        args = "/c mock_maa.cmd"
        start_mode = "open"                  # no clicking / hotkey needed
        timeout_min = 10
        close_after = $true
        kill_names = @("MAA.exe")
    }
    dismiss_maaend_popups = $false
    dismiss_timeout_min = 25
    hotkey = "ctrl+shift+alt+l"
    log_dir = (Join-Path $root "logs")       # logs stay inside this folder
}
$jsonPath = Join-Path $root "config.json"
[IO.File]::WriteAllText($jsonPath, ($cfg | ConvertTo-Json -Depth 5),
    (New-Object System.Text.UTF8Encoding($false)))
Write-Host "[OK] config.json (gate=all-day / success->shutdown / failure->keep on)"

Write-Host ""
Write-Host "=== ready. run in order: ===" -ForegroundColor Cyan
Write-Host "1) dry drill (seconds, launches nothing):"
Write-Host "     MaaAutoBoot.exe --boot --force --dryrun"
Write-Host "2) full mock run (~1 min, VM only if shutdown on!):"
Write-Host "     MaaAutoBoot.exe --boot --force"
Write-Host "   watch live log:"
Write-Host "     powershell -Command `"Get-Content logs\maa_autoboot.log -Wait -Tail 30`""
Write-Host "3) unattended chain test (VM recommended): admin PowerShell"
Write-Host '     $env:MAAAUTOBOOT_TASK_NAME="MaaAutoBootTest"; .\MaaAutoBoot.exe --install'
Write-Host "   then REBOOT. Auto-run mock after logon -> VM powers off = chain OK."
Write-Host "4) cleanup:"
Write-Host '     $env:MAAAUTOBOOT_TASK_NAME="MaaAutoBootTest"; .\MaaAutoBoot.exe --uninstall'
Write-Host ""
Write-Host "WARNING: step 2 shuts the machine down on success (grace 15s)." -ForegroundColor Yellow
Write-Host "         On your HOST pc, keep shutdown.enabled=$false or stay inside the VM." -ForegroundColor Yellow
