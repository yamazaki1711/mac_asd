#!/usr/bin/env bash
# =============================================================================
# setup_mac.sh — Автоматическая настройка Mac Studio M4 Max для ASD v11
# =============================================================================
# Проверяет и устанавливает: Homebrew, Miniforge, MLX, PostgreSQL, Redis
# Запускается один раз. Требует прав sudo для brew install.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[ASD]${NC} $1"; }
warn()  { echo -e "${YELLOW}[ASD WARN]${NC} $1"; }
fail()  { echo -e "${RED}[ASD FAIL]${NC} $1"; exit 1; }

# ---------------------------------------------------------------------------
# 1. Homebrew
# ---------------------------------------------------------------------------
check_brew() {
  if command -v brew &>/dev/null; then
    log "Homebrew уже установлен: $(brew --version | head -1)"
  else
    log "Устанавливаю Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
    eval "$(/opt/homebrew/bin/brew shellenv)"
    log "Homebrew установлен"
  fi
}

# ---------------------------------------------------------------------------
# 2. Miniforge (conda для Apple Silicon)
# ---------------------------------------------------------------------------
check_miniforge() {
  if command -v conda &>/dev/null; then
    log "Conda доступен: $(conda --version)"
  else
    log "Устанавливаю Miniforge..."
    MINIFORGE_URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh"
    curl -L -o /tmp/miniforge.sh "$MINIFORGE_URL"
    bash /tmp/miniforge.sh -b -p "$HOME/miniforge3"
    "$HOME/miniforge3/bin/conda" init zsh
    source ~/.zshrc
    rm /tmp/miniforge.sh
    log "Miniforge установлен"
  fi
}

# ---------------------------------------------------------------------------
# 3. MLX-LM (Python окружение)
# ---------------------------------------------------------------------------
setup_mlx_env() {
  local env_name="asd_mlx"
  if conda env list | grep -q "$env_name"; then
    log "Conda-окружение $env_name уже существует"
  else
    log "Создаю conda-окружение $env_name с mlx-lm..."
    conda create -n "$env_name" python=3.11 -y
    source "$HOME/miniforge3/etc/profile.d/conda.sh"
    conda activate "$env_name"
    pip install mlx-lm fastmcp[cli] numpy Pillow httpx pydantic-settings
    pip install psycopg2-binary sqlalchemy pgvector asyncpg
    pip install google-api-python-client google-auth-2 google-auth-oauthlib
    conda deactivate
    log "Окружение $env_name готово"
  fi
}

# ---------------------------------------------------------------------------
# 4. PostgreSQL + Redis (через Docker)
# ---------------------------------------------------------------------------
check_docker() {
  if command -v docker &>/dev/null; then
    log "Docker доступен"
  else
    log "Устанавливаю Docker Desktop для Mac..."
    warn "Docker Desktop необходимо скачать вручную:"
    warn "https://docs.docker.com/desktop/install/mac-install/"
    warn "После установки — перезапустите этот скрипт"
    exit 1
  fi
}

start_infrastructure() {
  local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local compose_file="$script_dir/docker-compose.yml"

  if [ ! -f "$compose_file" ]; then
    fail "docker-compose.yml не найден в $script_dir"
  fi

  log "Запускаю PostgreSQL + Redis через Docker Compose..."
  docker compose -f "$compose_file" up -d
  log "Сервисы запущены. Проверка..."
  sleep 5
  docker compose -f "$compose_file" ps
}

# ---------------------------------------------------------------------------
# 5. Google Workspace credentials
# ---------------------------------------------------------------------------
check_google_credentials() {
  local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local creds_dir="$script_dir/../credentials"

  if [ -f "$creds_dir/google_service_account.json" ]; then
    log "Google Workspace credentials найдены"
  else
    warn "Google Workspace credentials НЕ найдены в $creds_dir/"
    warn "Скопируйте google_service_account.json в $creds_dir/"
    warn "Без credentials Google Sheets/Docs функции будут недоступны"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "=== ASD v11 — Настройка Mac Studio M4 Max ==="
  log "Архитектура: $(uname -m)"
  log "macOS: $(sw_vers -productVersion)"

  check_brew
  check_miniforge
  setup_mlx_env
  check_docker
  start_infrastructure
  check_google_credentials

  log "=== Настройка завершена ==="
  log ""
  log "Следующие шаги:"
  log "  1. conda activate asd_mlx"
  log "  2. Загрузите MLX-модели (автоматически при первом запуске)"
  log "  3. Запустите MCP-сервер: python -m mcp_servers.asd_core.server"
  log "  4. PostgreSQL: localhost:5433 (oleg / asd_password)"
  log "  5. Redis: localhost:6379"
  log ""
}

main "$@"
