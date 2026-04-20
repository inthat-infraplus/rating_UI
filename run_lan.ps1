$ErrorActionPreference = "Stop"

function Get-PythonBootstrapCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3.11")
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }

    throw "Python was not found in PATH. Install Python 3.11+ or create .venv manually first."
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found. Creating .venv..." -ForegroundColor Yellow
    $bootstrapCommand = Get-PythonBootstrapCommand
    $bootstrapExe = $bootstrapCommand[0]
    $bootstrapArgs = @()
    if ($bootstrapCommand.Length -gt 1) {
        $bootstrapArgs = $bootstrapCommand[1..($bootstrapCommand.Length - 1)]
    }
    & $bootstrapExe @bootstrapArgs -m venv .venv
}

if (-not (Test-Path $venvPython)) {
    throw "Failed to create .venv. Check that Python is installed correctly."
}

Write-Host "Installing/updating dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install -r requirements.txt

Write-Host ""
Write-Host "Starting Rating UI on http://192.168.120.231:8081" -ForegroundColor Green
Write-Host "Users in the same LAN should open: http://192.168.120.231:8081" -ForegroundColor Green
Write-Host ""

& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8081
