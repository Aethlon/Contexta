#!/usr/bin/env bash
# ==============================================================================
# Contexta — Universal Entrypoint & Platform Bootstrapper
# Supports: macOS (Apple Silicon / Intel), Linux (x86_64 / arm64), Windows (WSL/Bash)
# ==============================================================================
set -e

# ------------------------------------------------------------------------------
# 1. DOCKER CONTAINER EXECUTION MODE
# If MODE is explicitly set in the environment, run the designated container role.
# ------------------------------------------------------------------------------
if [ -n "$MODE" ] && [ "$MODE" != "host" ] && [ "$MODE" != "start" ]; then
    case "$MODE" in
        api)
            echo "Starting Contexta FastAPI Application..."
            exec uvicorn contexta.api.app:app --host 0.0.0.0 --port 8000
            ;;
        worker)
            echo "Starting Contexta Celery Worker..."
            exec celery -A contexta.workers.celery_app.celery_app worker --loglevel=info -Q extraction,embedding,maintenance,celery
            ;;
        beat)
            echo "Starting Contexta Celery Beat..."
            exec celery -A contexta.workers.celery_app.celery_app beat --loglevel=info
            ;;
        migrate)
            echo "Running Alembic Database Migrations..."
            exec alembic upgrade head
            ;;
        model-server)
            echo "Starting Contexta Local Qwen3 Model Server..."
            exec uvicorn contexta.workers.model_server:app --host 0.0.0.0 --port "${MODEL_SERVER_PORT:-8001}" --workers 1
            ;;
        mcp)
            echo "Starting Contexta Model Context Protocol (MCP) Server on port 8765..."
            exec python -m contexta.mcp --transport sse --host 0.0.0.0 --port 8765
            ;;
        *)
            echo "Unknown container MODE: '$MODE'. Defaulting to API."
            exec uvicorn contexta.api.app:app --host 0.0.0.0 --port 8000
            ;;
    esac
fi

# ------------------------------------------------------------------------------
# 2. HOST SYSTEM BOOTSTRAPPER MODE (macOS / Linux / Windows WSL / Git Bash)
# ------------------------------------------------------------------------------

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
NC="\033[0m" # No Color

# Detect Platform
OS="$(uname -s 2>/dev/null || echo "Unknown")"
ARCH="$(uname -m 2>/dev/null || echo "Unknown")"

case "$OS" in
    Darwin*)
        PLATFORM="macOS ($ARCH)"
        ;;
    Linux*)
        PLATFORM="Linux ($ARCH)"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        PLATFORM="Windows Bash ($ARCH)"
        ;;
    *)
        PLATFORM="$OS ($ARCH)"
        ;;
esac

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "  ╔═══════════════════════════════════════════════════════════════╗"
    echo "  ║                       C O N T E X T A                         ║"
    echo "  ║          Sovereign Memory Intelligence for AI Agents          ║"
    echo "  ╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "${BLUE}Detected Platform:${NC} ${BOLD}$PLATFORM${NC}"
}

check_prerequisites() {
    # 1. Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Docker is not installed or not found in PATH.${NC}"
        echo ""
        echo "Please install Docker Desktop or Docker Engine:"
        echo "  • macOS:   https://docs.docker.com/desktop/install/mac-install/"
        echo "  • Linux:   https://docs.docker.com/engine/install/"
        echo "  • Windows: https://docs.docker.com/desktop/install/windows-install/"
        exit 1
    fi

    # 2. Check Docker daemon running
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Docker daemon is not running.${NC}"
        case "$OS" in
            Darwin*)
                echo "Please launch Docker Desktop from Applications."
                ;;
            Linux*)
                echo "Please start the Docker service with:"
                echo "  sudo systemctl start docker"
                ;;
            *)
                echo "Please ensure Docker Desktop or the Docker service is running."
                ;;
        esac
        exit 1
    fi

    # 3. Resolve Docker Compose command
    if docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker-compose"
    else
        echo -e "${RED}[ERROR] Neither 'docker compose' (v2) nor 'docker-compose' (v1) was found.${NC}"
        echo "Please install Docker Compose."
        exit 1
    fi

    # 4. Check .env file
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            echo -e "${YELLOW}[INFO] .env not found. Initializing from .env.example...${NC}"
            cp .env.example .env
            echo -e "${GREEN}[OK] .env initialized with offline-first defaults.${NC}"
        else
            echo -e "${YELLOW}[WARN] Neither .env nor .env.example found. Continuing with environment defaults.${NC}"
        fi
    fi

    # 5. Ensure dev TLS certificates exist for HTTPS gateway (:8443)
    if [ ! -f certs/cert.pem ] || [ ! -f certs/key.pem ]; then
        echo -e "${YELLOW}[INFO] Generating self-signed TLS certificates for secure HTTPS gateway...${NC}"
        mkdir -p certs
        if command -v openssl >/dev/null 2>&1; then
            openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -sha256 -days 365 -nodes -subj "/CN=localhost/O=Contexta Sovereign" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
            echo -e "${GREEN}[OK] TLS certificates created in ./certs${NC}"
        fi
    fi
}

show_help() {
    print_banner
    echo "Usage: ./entrypoint.sh [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start       (Default) Boot full offline-first stack in background"
    echo "  dev         Start full stack in foreground with live streaming logs"
    echo "  stop        Stop and gracefully tear down all running containers"
    echo "  restart     Restart all services"
    echo "  status      Check health status of all running containers"
    echo "  logs        Follow live aggregated container logs (or: ./entrypoint.sh logs api)"
    echo "  online      Start in Online BYOK mode (OpenAI / Cloud LLM)"
    echo "  enterprise  Start in Enterprise profile with gateway enforcement"
    echo "  models      Pre-download offline Qwen3 weights locally"
    echo "  help        Display this help message"
    echo ""
    echo "Platform Support:"
    echo "  • macOS:   ./entrypoint.sh start"
    echo "  • Linux:   ./entrypoint.sh start"
    echo "  • Windows: .\\start.ps1   or   bash entrypoint.sh start"
}

start_services() {
    local PROFILE_ARGS="$1"
    local ATTACH="$2"

    print_banner
    check_prerequisites

    echo ""
    echo -e "${GREEN}${BOLD}Booting Contexta Stack on $PLATFORM...${NC}"
    echo -e "${BLUE}Engine Mode:${NC} Offline-First (Local Qwen3 Embedding + Reranker)"
    echo ""

    # Resolve Dashboard port (default: 3000, fallback to 3001 if occupied)
    TARGET_PORT="${DASHBOARD_PORT:-3000}"
    if lsof -Pi :$TARGET_PORT -sTCP:LISTEN -t >/dev/null 2>&1 || nc -z 127.0.0.1 $TARGET_PORT 2>/dev/null; then
        # Check if port is occupied by our own container
        local IS_OUR_CONTAINER
        IS_OUR_CONTAINER=$(docker ps --filter "publish=$TARGET_PORT" --format "{{.Names}}" 2>/dev/null || true)
        if [ -z "$IS_OUR_CONTAINER" ]; then
            echo -e "${YELLOW}[NOTICE] Port $TARGET_PORT is already in use (e.g., local web-public).${NC}"
            TARGET_PORT="3001"
            echo -e "${YELLOW}[NOTICE] Binding Operator Dashboard to http://localhost:$TARGET_PORT${NC}"
            export DASHBOARD_PORT="$TARGET_PORT"
        fi
    fi

    if [ "$ATTACH" = "true" ]; then
        echo -e "${CYAN}Running in foreground (Ctrl+C to stop)...${NC}"
        $DOCKER_COMPOSE $PROFILE_ARGS up --build
    else
        echo -e "${CYAN}Building and launching services in background...${NC}"
        if ! $DOCKER_COMPOSE $PROFILE_ARGS up --build -d; then
            echo -e "${RED}[ERROR] Docker Compose failed to start services. See errors above.${NC}"
            echo -e "${YELLOW}Tip: Run './entrypoint.sh dev' for live container build output.${NC}"
            exit 1
        fi

        echo ""
        echo -e "${CYAN}Verifying stack services health...${NC}"
        local RETRY=0
        local MAX_RETRIES=25
        local ALL_HEALTHY=false

        while [ $RETRY -lt $MAX_RETRIES ]; do
            sleep 2
            RETRY=$((RETRY + 1))
            
            # Check if any container exited unexpectedly
            local EXITED_SVC
            EXITED_SVC=$(docker compose ps --filter "status=exited" --format "{{.Service}}" 2>/dev/null | grep -v "migration" || true)
            if [ -n "$EXITED_SVC" ]; then
                echo ""
                echo -e "${YELLOW}[WARNING] Service '$EXITED_SVC' exited unexpectedly.${NC}"
                docker compose logs --tail=20 "$EXITED_SVC"
                break
            fi

            # Check if core services are running
            local API_STATUS
            API_STATUS=$(docker compose ps api --format "{{.State}}" 2>/dev/null || true)
            local DASH_STATUS
            DASH_STATUS=$(docker compose ps dashboard --format "{{.State}}" 2>/dev/null || true)

            if [ "$API_STATUS" = "running" ] && [ "$DASH_STATUS" = "running" ]; then
                ALL_HEALTHY=true
                break
            fi
            printf "."
        done
        echo ""

        echo ""
        echo -e "${GREEN}${BOLD}✔ Contexta is up and running!${NC}"
        echo "─────────────────────────────────────────────────────────────"
        echo -e "  • ${BOLD}Operator Dashboard:${NC}   http://localhost:$TARGET_PORT"
        echo -e "  • ${BOLD}Contexta Brain API:${NC}   http://localhost:8000"
        echo -e "  • ${BOLD}HTTPS Secure Gateway:${NC} https://localhost:8443"
        echo -e "  • ${BOLD}MCP Server (SSE):${NC}      http://localhost:8765/sse"
        echo -e "  • ${BOLD}Local Model Server:${NC}   http://localhost:8001"
        echo "─────────────────────────────────────────────────────────────"
        echo -e "Default Dashboard Login: ${CYAN}User@aethlon.xyz${NC} / ${CYAN}password1234${NC}"
        echo ""
        echo "Helpful commands:"
        echo "  • View logs:    ./entrypoint.sh logs"
        echo "  • Check status: ./entrypoint.sh status"
        echo "  • Stop stack:   ./entrypoint.sh stop"
    fi
}

# ------------------------------------------------------------------------------
# Argument Routing
# ------------------------------------------------------------------------------
COMMAND="${1:-start}"
shift || true

case "$COMMAND" in
    start)
        start_services "" "false"
        ;;
    dev|foreground)
        start_services "" "true"
        ;;
    online)
        start_services "-f docker-compose.yml -f docker-compose.online.yml" "false"
        ;;
    enterprise)
        start_services "-f docker-compose.yml -f docker-compose.enterprise.yml" "false"
        ;;
    stop|down)
        print_banner
        check_prerequisites
        echo -e "${YELLOW}Stopping Contexta services...${NC}"
        $DOCKER_COMPOSE down
        echo -e "${GREEN}✔ Contexta stopped.${NC}"
        ;;
    restart)
        print_banner
        check_prerequisites
        echo -e "${YELLOW}Restarting Contexta services...${NC}"
        $DOCKER_COMPOSE restart
        echo -e "${GREEN}✔ Contexta restarted.${NC}"
        ;;
    status|ps)
        check_prerequisites
        $DOCKER_COMPOSE ps
        ;;
    logs)
        check_prerequisites
        $DOCKER_COMPOSE logs -f "$@"
        ;;
    models)
        print_banner
        echo -e "${CYAN}Pre-downloading offline models to ./models...${NC}"
        if command -v python3 >/dev/null 2>&1; then
            python3 scripts/download_offline_models.py
        elif command -v python >/dev/null 2>&1; then
            python scripts/download_offline_models.py
        else
            echo -e "${RED}[ERROR] Python is required to run the download script.${NC}"
            exit 1
        fi
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
