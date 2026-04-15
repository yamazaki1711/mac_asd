#!/usr/bin/env bash
# =============================================================================
# setup_mac.sh — Автоматическая настройка Mac Studio M4 Max для АСД
# =============================================================================
# Проверяет и устанавливает: Homebrew, Miniforge, Ollama, Neo4j, Redis
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
# 3. Ollama
# ---------------------------------------------------------------------------
check_ollama() {
  if command -v ollama &>/dev/null; then
    log "Ollama доступен: $(ollama --version)"
  else
    log "Устанавливаю Ollama..."
    brew install --cask ollama
    log "Ollama установлен. Запуск сервиса..."
    brew services start ollama
  fi

  # Pull required models (если ещё не скачаны)
  local models=("qwen3:32b" "deepseek-v3:latest")
  for model in "${models[@]}"; do
    if ollama list 2>/dev/null | grep -q "$model"; then
      log "Модель $model уже загружена"
    else
      log "Загружаю модель $model (это может занять время)..."
      ollama pull "$model" || warn "Не удалось загрузить $model — загрузите вручную: ollama pull $model"
    fi
  done
}

# ---------------------------------------------------------------------------
# 4. MLX-LM (Python окружение)
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
    pip install mlx-lm fastmcp[cli] numpy Pillow
    conda deactivate
    log "Окружение $env_name готово"
  fi
}

# ---------------------------------------------------------------------------
# 5. Neo4j + Redis (через Docker)
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

  log "Запускаю Neo4j + Redis через Docker Compose..."
  docker compose -f "$compose_file" up -d
  log "Сервисы запущены. Проверка..."
  sleep 5
  docker compose -f "$compose_file" ps
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "=== АСД v10 — Настройка Mac Studio ==="
  log "Архитектура: $(uname -m)"
  log "macOS: $(sw_vers -productVersion)"

  check_brew
  check_miniforge
  setup_mlx_env
  check_ollama
  check_docker
  start_infrastructure

  log "=== Настройка завершена ==="
  log ""
  log "Следующие шаги:"
  log "  1. conda activate asd_mlx"
  log "  2. Загрузите MLX-модели: python -c \"from mlx_lm import load; load('mlx-community/Meta-Llama-3.3-70B-Instruct-4bit')\""
  log "  3. Запустите MCP-сервер: python -m mcp_servers.asd_core.server"
  log "  4. Neo4j Browser: http://localhost:7474 (neo4j / asd_secret)"
  log ""
}

main "$@"
