param()

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSEdition -ne "Desktop") {
    $windowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if (-not $windowsPowerShell) {
        throw "Windows PowerShell (powershell.exe) was not found. Run this script from Windows PowerShell 5.1."
    }

    & $windowsPowerShell.Source -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
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

$features = @(
    "IIS-WebServerRole",
    "IIS-WebServer",
    "IIS-CommonHttpFeatures",
    "IIS-StaticContent",
    "IIS-DefaultDocument",
    "IIS-HttpErrors",
    "IIS-HttpRedirect",
    "IIS-ApplicationDevelopment",
    "IIS-ISAPIExtensions",
    "IIS-ISAPIFilter",
    "IIS-HealthAndDiagnostics",
    "IIS-HttpLogging",
    "IIS-Security",
    "IIS-RequestFiltering",
    "IIS-Performance",
    "IIS-WebServerManagementTools",
    "IIS-ManagementConsole",
    "IIS-ManagementScriptingTools"
)

Write-Host "Enabling IIS Windows features..." -ForegroundColor Cyan
$featureResult = Enable-WindowsOptionalFeature -Online -All -FeatureName $features -NoRestart

Write-Host ""
Write-Host "IIS prerequisites enabled." -ForegroundColor Green
if ($featureResult.RestartNeeded) {
    Write-Host "Windows restart is required before IIS management modules become available." -ForegroundColor Yellow
}
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart Windows if requested."
Write-Host "2. Install IIS URL Rewrite Module."
Write-Host "3. Install Application Request Routing (ARR)."
Write-Host "4. Re-run .\deployment\iis\setup_iis_proxy.ps1"
