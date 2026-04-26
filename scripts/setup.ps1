# =============================================================================
# CryptoPulse - Bootstrap para Windows (PowerShell)
#
# Uso:
#   .\scripts\setup.ps1                # Fase 1 (batch) - rapido
#   .\scripts\setup.ps1 -Full          # Todo el stack (incluye streaming/ML)
#
# Si te da error de ExecutionPolicy, ejecuta primero:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# =============================================================================
# Forzar UTF-8 en la salida para evitar caracteres corruptos
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

param(
    [switch]$Full,
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[!!] $msg" -ForegroundColor Yellow }

# -----------------------------------------------------------------
# 1. Detectar un Python valido
# -----------------------------------------------------------------
Write-Step "Detectando Python ..."

function Test-PythonCommand {
    param([string]$Exe, [string[]]$Args)
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return $null }
    try {
        $ver = & $Exe @Args --version 2>&1 | Out-String
        $ver = $ver.Trim()
        if ($ver -match "Python 3\.(9|10|11|12|13)") {
            return @{ Exe = $Exe; Args = $Args; Version = $ver }
        }
    } catch { }
    return $null
}

$detected = $null
# Probar "py" con distintas versiones (py launcher de Windows)
foreach ($v in @("-$PythonVersion", "-3.11", "-3.12", "-3.10", "-3.9", "-3")) {
    $detected = Test-PythonCommand -Exe "py" -Args @($v)
    if ($detected) { break }
}
# Caer a python / python3 a secas
if (-not $detected) {
    foreach ($e in @("python", "python3", "python.exe")) {
        $detected = Test-PythonCommand -Exe $e -Args @()
        if ($detected) { break }
    }
}

if (-not $detected) {
    Write-Host ""
    Write-Host "No se detecto Python 3.9+ en el PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Prueba ejecutar manualmente para ver que tienes:" -ForegroundColor Yellow
    Write-Host "  py --version"
    Write-Host "  python --version"
    Write-Host "  where.exe python"
    Write-Host ""
    Write-Host "Si ninguno responde, instala Python 3.11 desde:" -ForegroundColor Yellow
    Write-Host "  https://www.python.org/downloads/release/python-3119/"
    Write-Host "  (marca 'Add python.exe to PATH' en el instalador)"
    exit 1
}

$pythonExe  = $detected.Exe
$pythonArgs = $detected.Args
Write-Ok ("Python detectado: {0} {1} -> {2}" -f $pythonExe, ($pythonArgs -join ' '), $detected.Version)

# -----------------------------------------------------------------
# 2. Crear venv
# -----------------------------------------------------------------
Write-Step "Creando entorno virtual en .venv ..."

if (Test-Path ".venv") {
    Write-Warn ".venv ya existe. Se reutiliza. (Borra la carpeta si quieres empezar limpio)"
} else {
    & $pythonExe @pythonArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Fallo creando venv" }
    Write-Ok "venv creado"
}

$venvPy  = ".\.venv\Scripts\python.exe"
$venvPip = ".\.venv\Scripts\pip.exe"

if (-not (Test-Path $venvPy)) {
    throw "No se encontro $venvPy tras crear el venv"
}

# -----------------------------------------------------------------
# 3. Actualizar pip, wheel, setuptools
# -----------------------------------------------------------------
Write-Step "Actualizando pip/wheel/setuptools ..."
& $venvPy -m pip install --upgrade pip wheel setuptools 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Fallo actualizando pip" }
Write-Ok "pip actualizado"

# -----------------------------------------------------------------
# 4. Instalar requirements
# -----------------------------------------------------------------
$reqFile = if ($Full) { "requirements.txt" } else { "requirements-batch.txt" }
Write-Step "Instalando dependencias desde $reqFile ..."

& $venvPip install -r $reqFile 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Fallo instalando dependencias" }
Write-Ok "Dependencias instaladas"

# -----------------------------------------------------------------
# 5. Verificacion rapida
# -----------------------------------------------------------------
Write-Step "Verificando imports ..."
$check = @"
import sys
sys.path.insert(0, '.')
from ingestion.utils.config import settings
from ingestion.utils.minio_client import MinIOClient
from ingestion.batch import coingecko_loader, fng_loader
print('imports OK, tracked symbols:', settings.symbols_list[:3], '...')
"@
& $venvPy -c $check
if ($LASTEXITCODE -ne 0) { throw "Fallo en imports" }

Write-Host "`n=== SETUP COMPLETO ===" -ForegroundColor Green
Write-Host "Para activar el entorno en esta terminal:"
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "Si te da error de ExecutionPolicy, antes corre:"
Write-Host "  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" -ForegroundColor Yellow
Write-Host ""
Write-Host "Siguientes pasos:"
Write-Host "  $venvPy -m pytest tests/test_coingecko_loader.py -v"
Write-Host "  $venvPy -m ingestion.batch.coingecko_loader"
Write-Host "  $venvPy -m ingestion.batch.fng_loader"
Write-Host "  $venvPy -m ingestion.batch.run_all"
