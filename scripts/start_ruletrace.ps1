param(
    [switch]$PreviewOnly,
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendDir = Join-Path $ProjectRoot "backend"
$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found."
    }
}

function Test-LocalPort([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

Require-Command "node"
Require-Command "npm"

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    if ($SkipInstall) { throw "frontend/node_modules is missing and -SkipInstall was supplied." }
    Push-Location $FrontendDir
    try { npm ci } finally { Pop-Location }
}

Push-Location $FrontendDir
try { npm run build } finally { Pop-Location }

if ($PreviewOnly) {
    if (-not (Test-LocalPort 4173)) {
        Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "preview", "--", "--host", "127.0.0.1") -WorkingDirectory $FrontendDir -WindowStyle Hidden
    }
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:4173/" }
    Write-Host "RuleTrace Scholar preview: http://127.0.0.1:4173/"
    exit 0
}

if (-not (Test-Path $PythonExe)) {
    if ($SkipInstall) { throw ".venv is missing and -SkipInstall was supplied." }
    Require-Command "uv"
    & uv venv --python 3.13 $VenvDir
}

if (-not $SkipInstall) {
    & uv pip install --python $PythonExe -r (Join-Path $BackendDir "requirements.txt")
}

$EnvFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $BackendDir ".env.example") -Destination $EnvFile
    Write-Warning "Created backend/.env. Review the LLM and service endpoints before production use."
}

$Missing = @()
if (-not (Test-LocalPort 5432)) { $Missing += "PostgreSQL :5432" }
if (-not (Test-LocalPort 19530)) { $Missing += "Milvus :19530" }
if (-not (Test-LocalPort 11434)) { $Missing += "OpenAI-compatible LLM/Ollama :11434" }
if ($Missing.Count -gt 0) {
    throw "Full mode cannot start because these services are unavailable: $($Missing -join ', '). Use -PreviewOnly to inspect the UI."
}

if (-not (Test-LocalPort 8000)) {
    Start-Process -FilePath $PythonExe -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $BackendDir -WindowStyle Hidden
}

if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8000/" }
Write-Host "RuleTrace Scholar: http://127.0.0.1:8000/"
