$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BundledPython = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VendorDjangoInit = Join-Path $ProjectRoot "vendor\django\__init__.py"

function Resolve-Python {
    if (Test-Path $VenvPython) {
        return $VenvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    if (Test-Path $BundledPython) {
        return $BundledPython
    }

    throw "Python was not found. Install Python 3.12+ or use the bundled runtime on this machine."
}

function Test-Django {
    param(
        [string]$PythonExe
    )

    if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
        return $false
    }

    if (Test-Path $VendorDjangoInit) {
        $env:PYTHONPATH = Join-Path $ProjectRoot "vendor"
    } else {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }

    & $PythonExe -c "import django" *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-Venv {
    param(
        [string]$BootstrapPython
    )

    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating local virtual environment..." -ForegroundColor Cyan
        & $BootstrapPython -m venv (Join-Path $ProjectRoot ".venv")
    }

    Write-Host "Installing SalariQ requirements..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

$PythonExe = Resolve-Python
if (-not (Test-Django -PythonExe $PythonExe)) {
    Ensure-Venv -BootstrapPython $PythonExe
    $PythonExe = $VenvPython
}

Write-Host "Preparing SalariQ..." -ForegroundColor Cyan

& $PythonExe (Join-Path $ProjectRoot "manage.py") migrate --noinput
& $PythonExe (Join-Path $ProjectRoot "manage.py") seed_salariq_starter
& $PythonExe (Join-Path $ProjectRoot "manage.py") ensure_default_admin --username admin --email admin@salariq.local --password SalariQ2026!

Write-Host ""
Write-Host "SalariQ is ready." -ForegroundColor Green
Write-Host "No sites were preloaded. Add your own from the Sites screen." -ForegroundColor Yellow
Write-Host "Login: admin" -ForegroundColor Yellow
Write-Host "Password: SalariQ2026!" -ForegroundColor Yellow
Write-Host "Motto: SMART PAYROLL. HAPPY PEOPLE." -ForegroundColor Yellow
Write-Host "Opening local server at http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host ""

$ServerUrl = "http://127.0.0.1:8000/"
Start-Process powershell -ArgumentList "-NoProfile", "-Command", "Start-Sleep -Seconds 3; Start-Process '$ServerUrl'" -WindowStyle Hidden | Out-Null

& $PythonExe (Join-Path $ProjectRoot "manage.py") runserver 127.0.0.1:8000
