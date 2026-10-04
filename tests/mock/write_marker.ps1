param(
    [Parameter(Mandatory = $true)][string]$File,
    [Parameter(Mandatory = $true)][string]$Text
)
# Appends one UTF-8 (no BOM) line. MaaAutoBoot decodes logs strictly
# as UTF-8, so the Chinese marker "任务已全部完成！" must be UTF-8 bytes.
$dir = Split-Path -Parent $File
if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Text
[IO.File]::AppendAllText($File, $line + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false)))
Write-Host "marker -> $File : $Text"
