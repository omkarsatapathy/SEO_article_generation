#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# launch.sh — Start the SEO Article Generation system locally
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Default uv environment lives in a hidden folder to avoid package discovery conflicts
DEFAULT_UV_ENV="$PROJECT_DIR/.uv/graph_env"
UV_ENV_PATH="${UV_VENV_PATH:-$DEFAULT_UV_ENV}"

# ── Colours ─────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

info()  { echo -e "${CYAN}ℹ  ${NC}$*"; }
ok()    { echo -e "${GREEN}✅ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠️  ${NC}$*"; }
error() { echo -e "${RED}❌ ${NC}$*"; exit 1; }

# ── 1. Check .env file ─────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        warn ".env not found — copying .env.example to .env"
        cp .env.example .env
        warn "Please edit .env and set OPENAI_API_KEY before using the LLM features."
    else
        error "No .env or .env.example found. Create a .env file with required variables."
    fi
fi
ok ".env file present"

# ── 2. Ensure uv-managed env exists and is activated ────────
if ! command -v uv &>/dev/null; then
    error "uv not installed. Install from https://docs.astral.sh/uv/getting-started/ then re-run."
fi

ACTIVE_ENV="${VIRTUAL_ENV:-${CONDA_PREFIX:-}}"
RESPECT_ACTIVE="${UV_RESPECT_ACTIVE:-1}"

if [ -n "$ACTIVE_ENV" ] && [ "$RESPECT_ACTIVE" = "1" ]; then
    info "Using already-active environment at $ACTIVE_ENV"
else
    if [ ! -d "$UV_ENV_PATH" ]; then
        mkdir -p "$(dirname "$UV_ENV_PATH")"
        info "Creating uv virtual environment at $UV_ENV_PATH..."
        uv venv "$UV_ENV_PATH"
        ok "uv environment created"
    fi

    info "Activating environment..."
    # shellcheck source=/dev/null
    source "$UV_ENV_PATH/bin/activate"
    ACTIVE_ENV="$UV_ENV_PATH"
    ok "Environment activated ($(python --version))"
fi

# ── 3. Install dependencies ─────────────────────────────────
info "Installing dependencies from pyproject.toml via uv (including [dev])..."
uv pip install -q .[dev]
ok "Dependencies installed"

# ── 4. Start PostgreSQL via Docker (optional) ──────────────
DB_READY=false
if command -v docker &>/dev/null; then
    if docker compose ps db 2>/dev/null | grep -q "running"; then
        ok "PostgreSQL container already running"
        DB_READY=true
    else
        info "Starting PostgreSQL via Docker Compose..."
        if docker compose up -d db 2>/dev/null; then
            info "Waiting for PostgreSQL to be healthy..."
            retries=0
            until docker compose exec db pg_isready -U seo_user -d seo_agent &>/dev/null; do
                retries=$((retries + 1))
                if [ $retries -ge 30 ]; then
                    warn "PostgreSQL did not become ready within 30 seconds. Continuing without DB."
                    break
                fi
                sleep 1
            done
            if [ $retries -lt 30 ]; then
                ok "PostgreSQL is ready"
                DB_READY=true
            fi
        else
            warn "Docker Compose failed (is Docker Desktop running?). Continuing without DB."
            warn "The API server needs PostgreSQL — start Docker Desktop and re-run to use full features."
        fi
    fi
else
    warn "Docker not found. Skipping database startup."
    warn "Make sure PostgreSQL is running and DATABASE_URL in .env is correct."
fi

# ── 5. Run tests to verify setup ────────────────────────────
echo ""
info "Running tests to verify everything works..."
echo "─────────────────────────────────────────────"
python -m pytest tests/ -v --tb=short -m "not integration" 2>&1 | tail -20
echo "─────────────────────────────────────────────"
ok "Tests completed"

# ── 6. Launch the FastAPI server ─────────────────────────────
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   SEO Article Generation API — Starting Up         ║${NC}"
echo -e "${GREEN}╠════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  API:     http://localhost:8000                    ║${NC}"
echo -e "${GREEN}║  Docs:    http://localhost:8000/docs               ║${NC}"
echo -e "${GREEN}║  Health:  http://localhost:8000/health             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
