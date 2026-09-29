param(
    [int]$MaxAttempts = 8,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $ProjectRoot "setup-progress.log"
$HealthUrl = "http://localhost:8000/api/health"
$AppUrl = "http://localhost:5173"

function Write-SetupLog([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    $line | Tee-Object -FilePath $LogFile -Append
}

function Wait-Docker([int]$Attempts = 8) {
    for ($dockerAttempt = 1; $dockerAttempt -le $Attempts; $dockerAttempt++) {
        docker version --format '{{.Server.Version}}' *> $null
        if ($LASTEXITCODE -eq 0) {
            return $true
        }

        Write-SetupLog "Docker is not ready (attempt $dockerAttempt/$Attempts)."
        $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path -LiteralPath $desktop) {
            Start-Process -FilePath $desktop
        }
        Start-Sleep -Seconds 15
    }
    return $false
}

Set-Location -LiteralPath $ProjectRoot
Set-Content -LiteralPath $LogFile -Value "RuleTrace Scholar automated setup"
Write-SetupLog "Project root: $ProjectRoot"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-SetupLog "ERROR: Docker CLI was not found."
    exit 1
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-SetupLog "ERROR: Ollama CLI was not found."
    exit 1
}

$dockerReady = Wait-Docker -Attempts $MaxAttempts

if (-not $dockerReady) {
    Write-SetupLog "ERROR: Docker Engine did not become ready."
    exit 1
}
Write-SetupLog "Docker Engine is ready."

$modelReady = $false
for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    Write-SetupLog "Pulling qwen3:8b (attempt $attempt/$MaxAttempts). Existing partial data will be resumed."
    & ollama pull qwen3:8b 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -eq 0) {
        $modelReady = $true
        Write-SetupLog "qwen3:8b is ready."
        break
    }
    Write-SetupLog "Model pull was interrupted; retrying in 15 seconds."
    Start-Sleep -Seconds 15
}

if (-not $modelReady) {
    Write-SetupLog "ERROR: qwen3:8b could not be downloaded after $MaxAttempts attempts."
    exit 1
}

$composeReady = $false
for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    if (-not (Wait-Docker -Attempts $MaxAttempts)) {
        Write-SetupLog "Docker Engine could not be restored before Compose attempt $attempt."
        continue
    }
    Write-SetupLog "Building and starting Docker services (attempt $attempt/$MaxAttempts)."
    & docker compose up --build -d 2>&1 | Tee-Object -FilePath $LogFile -Append
    if ($LASTEXITCODE -eq 0) {
        $composeReady = $true
        Write-SetupLog "Docker Compose services were started."
        break
    }
    Write-SetupLog "Docker Compose was interrupted; retrying in 15 seconds."
    Start-Sleep -Seconds 15
}

if (-not $composeReady) {
    Write-SetupLog "ERROR: Docker Compose could not finish after $MaxAttempts attempts."
    exit 1
}

$deadline = (Get-Date).AddMinutes(30)
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 120
        Write-SetupLog "Health: ok=$($health.ok), milvus=$($health.milvus), llm=$($health.llm), metadata=$($health.metadata)"
        if ($health.ok) {
            Write-SetupLog "SUCCESS: RuleTrace Scholar is ready at $AppUrl"
            if (-not $NoBrowser) {
                Start-Process $AppUrl
            }
            exit 0
        }
    }
    catch {
        Write-SetupLog "Waiting for backend initialization: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 20
}

Write-SetupLog "ERROR: Services started, but the health check did not become ready within 30 minutes."
exit 1
