param(
    [string]$HostName = "rating-ui.infra.local",
    [string]$ServerIp = "192.168.120.231"
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSEdition -ne "Desktop") {
    $windowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if (-not $windowsPowerShell) {
        throw "Windows PowerShell (powershell.exe) was not found. Run this script from Windows PowerShell 5.1."
    }

    & $windowsPowerShell.Source -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -HostName $HostName -ServerIp $ServerIp
    exit $LASTEXITCODE
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    throw "Run this script in an elevated PowerShell window (Run as Administrator)."
}

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$existingLines = if (Test-Path $hostsPath) { Get-Content $hostsPath } else { @() }
$escapedHostName = [regex]::Escape($HostName)
$filtered = $existingLines | Where-Object { $_ -notmatch "^\s*\d{1,3}(\.\d{1,3}){3}\s+$escapedHostName(\s|$)" }
$updated = @($filtered + "$ServerIp`t$HostName")
Set-Content -Path $hostsPath -Value $updated -Encoding ASCII

Write-Host "Hosts entry added: $HostName -> $ServerIp" -ForegroundColor Green
