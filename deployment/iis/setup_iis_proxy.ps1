param(
    [string]$SiteName = "RatingUI",
    [string]$HostName = "rating-ui.infra.local",
    [int]$FrontendPort = 80,
    [int]$BackendPort = 8081,
    [string]$ServerIp = "192.168.120.231",
    [switch]$OpenFirewall = $true,
    [switch]$AddLocalHostsEntry
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSEdition -ne "Desktop") {
    $windowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if (-not $windowsPowerShell) {
        throw "Windows PowerShell (powershell.exe) was not found. Run this script from Windows PowerShell 5.1."
    }

    $relaunchArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-SiteName", $SiteName,
        "-HostName", $HostName,
        "-FrontendPort", "$FrontendPort",
        "-BackendPort", "$BackendPort",
        "-ServerIp", $ServerIp
    )
    if ($OpenFirewall) {
        $relaunchArgs += "-OpenFirewall"
    }
    if ($AddLocalHostsEntry) {
        $relaunchArgs += "-AddLocalHostsEntry"
    }

    & $windowsPowerShell.Source @relaunchArgs
    exit $LASTEXITCODE
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-HostsEntry {
    param(
        [string]$IpAddress,
        [string]$Name
    )

    $hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
    $existingLines = if (Test-Path $hostsPath) { Get-Content $hostsPath } else { @() }
    $escapedIpAddress = [regex]::Escape($IpAddress)
    $escapedName = [regex]::Escape($Name)
    $filtered = $existingLines | Where-Object { $_ -notmatch "^\s*$escapedIpAddress\s+$escapedName\s*$" -and $_ -notmatch "^\s*\d{1,3}(\.\d{1,3}){3}\s+$escapedName(\s|$)" }
    $updated = @($filtered + "$IpAddress`t$Name")
    Set-Content -Path $hostsPath -Value $updated -Encoding ASCII
}

function Grant-SiteReadAccess {
    param(
        [string]$Path,
        [string]$AppPoolName
    )

    $appPoolIdentity = "IIS AppPool\$AppPoolName"
    & icacls $Path /grant "${appPoolIdentity}:(OI)(CI)RX" /t | Out-Null
    & icacls $Path /grant "IIS_IUSRS:(OI)(CI)RX" /t | Out-Null
}

if (-not (Test-IsAdmin)) {
    throw "Run this script in an elevated PowerShell window (Run as Administrator)."
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteRoot = Join-Path $scriptRoot "site"
$webConfigSource = Join-Path $scriptRoot "web.config"
$webConfigTarget = Join-Path $siteRoot "web.config"
$proxyTarget = "http://127.0.0.1:{0}" -f $BackendPort
$frontendFirewallRule = "Rating UI Frontend {0}" -f $FrontendPort

if (-not (Get-Module -ListAvailable -Name WebAdministration)) {
    throw "IIS WebAdministration module is not available. Enable IIS with Management Scripts and Tools first."
}

Import-Module WebAdministration

if (-not (Test-Path $siteRoot)) {
    New-Item -ItemType Directory -Path $siteRoot | Out-Null
}

Copy-Item -Path $webConfigSource -Destination $webConfigTarget -Force

if (-not (Test-Path "IIS:\AppPools\$SiteName")) {
    New-WebAppPool -Name $SiteName | Out-Null
}

Set-ItemProperty "IIS:\AppPools\$SiteName" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$SiteName" -Name processModel.identityType -Value "ApplicationPoolIdentity"

if (-not (Test-Path "IIS:\Sites\$SiteName")) {
    New-Website -Name $SiteName -PhysicalPath $siteRoot -Port $FrontendPort -HostHeader $HostName -ApplicationPool $SiteName | Out-Null
} else {
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $siteRoot
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name applicationPool -Value $SiteName
}

Grant-SiteReadAccess -Path $siteRoot -AppPoolName $SiteName

$bindingInfo = "*:{0}:{1}" -f $FrontendPort, $HostName
if (-not (Get-WebBinding -Name $SiteName -Protocol "http" | Where-Object { $_.bindingInformation -eq $bindingInfo })) {
    New-WebBinding -Name $SiteName -Protocol "http" -Port $FrontendPort -HostHeader $HostName | Out-Null
}

& "$env:SystemRoot\System32\inetsrv\appcmd.exe" set config -section:system.webServer/proxy /enabled:"True" /preserveHostHeader:"True" /reverseRewriteHostInResponseHeaders:"False" | Out-Null

if ($OpenFirewall) {
    if (-not (Get-NetFirewallRule -DisplayName $frontendFirewallRule -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $frontendFirewallRule -Direction Inbound -Protocol TCP -LocalPort $FrontendPort -Action Allow | Out-Null
    }
}

if ($AddLocalHostsEntry) {
    Ensure-HostsEntry -IpAddress $ServerIp -Name $HostName
}

Write-Host ""
Write-Host "IIS reverse proxy configured." -ForegroundColor Green
Write-Host "Site Name     : $SiteName"
Write-Host "Host Name     : $HostName"
Write-Host "Frontend URL  : http://$HostName" -ForegroundColor Green
Write-Host "Frontend Port : $FrontendPort"
Write-Host "Proxy Target  : $proxyTarget"
Write-Host "Server IP     : $ServerIp"
Write-Host ""
Write-Host "What this script already did:" -ForegroundColor Cyan
Write-Host "1. Configured IIS site and app pool."
Write-Host "2. Bound http://$HostName on port $FrontendPort."
Write-Host "3. Enabled ARR proxy mode in IIS."
if ($OpenFirewall) {
    Write-Host "4. Opened Windows Firewall inbound TCP port $FrontendPort."
}
if ($AddLocalHostsEntry) {
    Write-Host "5. Added a local hosts entry for $HostName -> $ServerIp."
}
Write-Host ""
Write-Host "Still required:" -ForegroundColor Yellow
Write-Host "1. Install IIS URL Rewrite Module."
Write-Host "2. Install Application Request Routing (ARR)."
Write-Host "3. Keep FastAPI running on port $BackendPort."
Write-Host "4. Point internal DNS or client hosts files to $ServerIp for $HostName."
