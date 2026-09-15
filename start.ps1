param (
    [string]$Command = 'start',
    [int]$DashboardPort = 0
)

$ErrorActionPreference = 'Stop'

function Write-Banner {
    Write-Host ''
    Write-Host '  +---------------------------------------------------------------+' -ForegroundColor Cyan
    Write-Host '  |                       C O N T E X T A                         |' -ForegroundColor Cyan
    Write-Host '  |          Sovereign Memory Intelligence for AI Agents          |' -ForegroundColor Cyan
    Write-Host '  +---------------------------------------------------------------+' -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Platform: Windows (PowerShell)' -ForegroundColor Blue
}

function Check-PortAvailable ([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -eq $connections)
}

function Check-Prerequisites {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host '[ERROR] Docker is not installed or not found in PATH.' -ForegroundColor Red
        Write-Host 'Please install Docker Desktop for Windows: https://docs.docker.com/desktop/install/windows-install/'
        Exit 1
    }

    try {
        docker info 2>&1 | Out-Null
    } catch {
        Write-Host '[ERROR] Docker Desktop daemon is not running.' -ForegroundColor Red
        Write-Host 'Please start Docker Desktop and wait for the engine to initialize.'
        Exit 1
    }

    if (-not (Test-Path '.env')) {
        if (Test-Path '.env.example') {
            Write-Host '[INFO] .env not found. Initializing from .env.example...' -ForegroundColor Yellow
            Copy-Item '.env.example' '.env'
            Write-Host '[OK] .env created with offline-first defaults.' -ForegroundColor Green
        }
    }

    if (-not (Test-Path 'certs/cert.pem') -or -not (Test-Path 'certs/key.pem')) {
        Write-Host '[INFO] Generating self-signed TLS certificates for secure HTTPS gateway...' -ForegroundColor Yellow
        New-Item -ItemType Directory -Force -Path 'certs' | Out-Null
        if (Get-Command openssl -ErrorAction SilentlyContinue) {
            openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -sha256 -days 365 -nodes -subj "/CN=localhost/O=Contexta Sovereign" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>$null
            Write-Host '[OK] TLS certificates created in .\certs' -ForegroundColor Green
        }
    }
}

function Resolve-DashboardPort {
    if ($DashboardPort -gt 0) {
        $env:DASHBOARD_PORT = "$DashboardPort"
        return $DashboardPort
    }

    if (-not (Check-PortAvailable 3000)) {
        # Check if port 3000 is occupied by a docker container named memento-dashboard or external app
        $isMementoContainer = $false
        try {
            $running = docker ps --filter "publish=3000" --format "{{.Names}}" 2>$null
            if ($running -match "dashboard|web") { $isMementoContainer = $true }
        } catch {}

        if (-not $isMementoContainer) {
            Write-Host '[NOTICE] Port 3000 is currently occupied (e.g., local web-public).' -ForegroundColor Yellow
            Write-Host '[NOTICE] Automatically binding Operator Dashboard to http://localhost:3001' -ForegroundColor Yellow
            $env:DASHBOARD_PORT = "3001"
            return 3001
        }
    }

    $env:DASHBOARD_PORT = "3000"
    return 3000
}

function Wait-ForServices ([int]$TargetPort) {
    Write-Host ''
    Write-Host 'Verifying stack services health...' -ForegroundColor Cyan

    $maxRetries = 25
    $retry = 0
    $allHealthy = $false

    while ($retry -lt $maxRetries) {
        Start-Sleep -Seconds 2
        $retry++

        $psOutput = docker compose ps --format json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($null -eq $psOutput) {
            Write-Host -NoNewline '.'
            continue
        }

        # Check for unexpected container exits
        $exited = $psOutput | Where-Object { $_.State -eq "exited" -and $_.Service -ne "migration" }
        if ($exited) {
            Write-Host ''
            Write-Host "[WARNING] Service '$($exited[0].Service)' stopped unexpectedly." -ForegroundColor Yellow
            Write-Host "Fetching recent service logs:" -ForegroundColor Yellow
            docker compose logs --tail=20 $($exited[0].Service)
            return $false
        }

        # Check if core database and brain API are up
        $apiContainer = $psOutput | Where-Object { $_.Service -eq "api" }
        $postgresContainer = $psOutput | Where-Object { $_.Service -eq "postgres" }

        $postgresReady = ($postgresContainer -and ($postgresContainer.Health -eq "healthy" -or $postgresContainer.State -eq "running"))
        $apiReady = ($apiContainer -and $apiContainer.State -eq "running")

        if ($postgresReady -and $apiReady) {
            $allHealthy = $true
            break
        }

        Write-Host -NoNewline '.'
    }

    Write-Host ''
    return $allHealthy
}

function Show-Help {
    Write-Banner
    Write-Host 'Usage: .\start.ps1 [COMMAND] [-DashboardPort <port>]'
    Write-Host ''
    Write-Host 'Commands:'
    Write-Host '  start       (Default) Boot full offline-first stack in background'
    Write-Host '  dev         Start full stack in foreground with live streaming logs'
    Write-Host '  stop        Stop and gracefully tear down all running containers'
    Write-Host '  restart     Restart all services'
    Write-Host '  status      Check health status of all running containers'
    Write-Host '  logs        Follow live aggregated container logs'
    Write-Host '  online      Start in Online BYOK mode (OpenAI / Cloud LLM)'
    Write-Host '  enterprise  Start in Enterprise profile with gateway enforcement'
    Write-Host '  help        Display this help message'
}

$action = $Command.ToLower()

if ($action -eq 'start') {
    Write-Banner
    Check-Prerequisites
    $resolvedPort = Resolve-DashboardPort

    Write-Host ''
    Write-Host "Booting Contexta Stack (Offline-First, Dashboard on :$resolvedPort)..." -ForegroundColor Green

    $process = Start-Process -FilePath "docker" -ArgumentList "compose up --build -d" -NoNewWindow -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        Write-Host ''
        Write-Host '[ERROR] Docker Compose failed to launch services. See errors above.' -ForegroundColor Red
        Write-Host 'Tip: Check container build errors by running: .\start.ps1 dev' -ForegroundColor Yellow
        Exit $process.ExitCode
    }

    $isReady = Wait-ForServices -TargetPort $resolvedPort

    Write-Host ''
    Write-Host '  [OK] Contexta stack launched successfully!' -ForegroundColor Green
    Write-Host '-------------------------------------------------------------' -ForegroundColor DarkGray
    Write-Host "  * Operator Dashboard:   http://localhost:$resolvedPort" -ForegroundColor White
    Write-Host '  * Contexta Brain API:   http://localhost:8000' -ForegroundColor White
    Write-Host '  * HTTPS Secure Gateway: https://localhost:8443' -ForegroundColor White
    Write-Host '  * MCP Server (SSE):      http://localhost:8765/sse' -ForegroundColor White
    Write-Host '  * Local Model Server:   http://localhost:8001' -ForegroundColor White
    Write-Host '-------------------------------------------------------------' -ForegroundColor DarkGray
    Write-Host 'Default Dashboard Login: User@aethlon.xyz / password1234' -ForegroundColor Cyan
    Write-Host ''
}
elseif ($action -eq 'dev') {
    Write-Banner
    Check-Prerequisites
    $resolvedPort = Resolve-DashboardPort
    Write-Host ''
    Write-Host "Running in foreground on :$resolvedPort (Ctrl+C to stop)..." -ForegroundColor Cyan
    docker compose up --build
}
elseif ($action -eq 'online') {
    Write-Banner
    Check-Prerequisites
    $resolvedPort = Resolve-DashboardPort
    Write-Host ''
    Write-Host 'Booting Contexta Online BYOK Profile...' -ForegroundColor Green
    $process = Start-Process -FilePath "docker" -ArgumentList "compose -f docker-compose.yml -f docker-compose.online.yml up --build -d" -NoNewWindow -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        Write-Host '[ERROR] Docker Compose failed to start Online Profile.' -ForegroundColor Red
        Exit $process.ExitCode
    }
    Wait-ForServices -TargetPort $resolvedPort
}
elseif ($action -eq 'enterprise') {
    Write-Banner
    Check-Prerequisites
    $resolvedPort = Resolve-DashboardPort
    Write-Host ''
    Write-Host 'Booting Contexta Enterprise Profile...' -ForegroundColor Green
    $process = Start-Process -FilePath "docker" -ArgumentList "compose -f docker-compose.yml -f docker-compose.enterprise.yml up --build -d" -NoNewWindow -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        Write-Host '[ERROR] Docker Compose failed to start Enterprise Profile.' -ForegroundColor Red
        Exit $process.ExitCode
    }
    Wait-ForServices -TargetPort $resolvedPort
}
elseif ($action -eq 'stop') {
    Write-Banner
    Check-Prerequisites
    Write-Host 'Stopping Contexta services...' -ForegroundColor Yellow
    docker compose down
    Write-Host '[OK] Contexta stopped gracefully.' -ForegroundColor Green
}
elseif ($action -eq 'restart') {
    Write-Banner
    Check-Prerequisites
    Write-Host 'Restarting Contexta services...' -ForegroundColor Yellow
    docker compose restart
    Write-Host '[OK] Contexta restarted.' -ForegroundColor Green
}
elseif ($action -eq 'status') {
    Check-Prerequisites
    docker compose ps
}
elseif ($action -eq 'logs') {
    Check-Prerequisites
    docker compose logs -f
}
elseif ($action -eq 'help') {
    Show-Help
}
else {
    Write-Host "Unknown command: $Command" -ForegroundColor Red
    Show-Help
    Exit 1
}
