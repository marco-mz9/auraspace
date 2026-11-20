[CmdletBinding()]
param(
    [ValidateSet("root", "local")]
    [string]$Location = "root",

    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $AppDir
$RequirementsPath = Join-Path $AppDir "requirements.txt"

if ($Location -eq "local") {
    $VenvDir = Join-Path $AppDir ".venv"
} else {
    $VenvDir = Join-Path $RepoRoot ".venv"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "=== Configuracion del entorno QA de AuraSpace ==="
Write-Host "Proyecto         : $AppDir"
Write-Host "Entorno virtual  : $VenvDir"
Write-Host "Dependencias     : $RequirementsPath"

if (-not (Test-Path $RequirementsPath)) {
    throw "No se encontro el archivo requirements.txt en: $RequirementsPath"
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creando entorno virtual..."
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo al crear el entorno virtual con '$Python'."
    }
} else {
    Write-Host "El entorno virtual ya existe. Se reutilizara."
}

Write-Host "Actualizando pip..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al actualizar pip."
}

Write-Host "Instalando dependencias desde requirements.txt..."
& $VenvPython -m pip install -r $RequirementsPath
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al instalar las dependencias."
}

Write-Host ""
Write-Host "Nota: No se descargan navegadores de Playwright; las pruebas E2E usan Microsoft Edge local."
Write-Host ""
Write-Host "=== Resumen de versiones instaladas ==="
& $VenvPython -c "import importlib.metadata as m, sys; pkgs=['Flask','pytest','pytest-cov','pytest-html','playwright']; print(f'Python: {sys.version.split()[0]}'); [print(f'{p}: {m.version(p)}') for p in pkgs]"
if ($LASTEXITCODE -ne 0) {
    throw "Fallo al consultar las versiones instaladas."
}

Write-Host ""
Write-Host "Para ejecutar las pruebas desde '$AppDir':"
Write-Host "  `"$VenvPython`" scripts\run_tests.py --suite base"
Write-Host "  `"$VenvPython`" scripts\run_tests.py --suite all"
