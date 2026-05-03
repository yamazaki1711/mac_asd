#!/usr/bin/env bash
# =============================================================================
# setup_linux.sh — Автоматическая настройка Linux для ASD v12.0
# =============================================================================
# Целевая машина: Ubuntu 24.04 / Debian 12, RTX 5060 8GB, DDR5 32GB, SSD 1TB
# Проверяет и устанавливает: NVIDIA drivers, CUDA, Ollama, Docker, PostgreSQL
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${GREEN}[ASD]${NC} $1"; }
warn()  { echo -e "${YELLOW}[ASD WARN]${NC} $1"; }
fail()  { echo -e "${RED}[ASD FAIL]${NC} $1"; exit 1; }
info()  { echo -e "${BLUE}[ASD INFO]${NC} $1"; }

# ---------------------------------------------------------------------------
# 0. Pre-flight: detect OS and hardware
# ---------------------------------------------------------------------------
detect_system() {
  log "=== ASD v12.0 — Linux Setup ==="
  log "Дата: $(date +%Y-%m-%d)"

  if [ -f /etc/os-release ]; then
    . /etc/os-release
    log "OS: $NAME $VERSION_ID"
  else
    warn "Не удалось определить ОС. Ожидается Ubuntu 24.04 или Debian 12."
  fi

  log "Kernel: $(uname -r)"
  log "Architecture: $(uname -m)"
  log "CPU: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"
  log "RAM: $(free -h | awk '/^Mem:/ {print $2}') total"
  log "Disk: $(df -h / | awk 'NR==2 {print $4}') available"

  # Check NVIDIA GPU
  if command -v nvidia-smi &>/dev/null; then
    log "NVIDIA GPU найдена:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true
  elif lspci 2>/dev/null | grep -iq nvidia; then
    warn "NVIDIA GPU обнаружена но драйвер не установлен. Будет установлен."
  else
    warn "NVIDIA GPU не обнаружена. LLM inference будет на CPU (медленно)."
  fi
}

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
install_system_packages() {
  log "Установка системных пакетов..."

  if [ "$(id -u)" -ne 0 ]; then
    warn "Для установки пакетов нужны права sudo. Запросите пароль если потребуется."
  fi

  sudo apt-get update -qq

  # Build essentials + Python
  sudo apt-get install -y -qq \
    build-essential \
    python3 python3-pip python3-venv python3-dev \
    curl wget git \
    pciutils \
    ca-certificates \
    gnupg \
    lsb-release \
    tesseract-ocr tesseract-ocr-rus \
    poppler-utils \
    libpq-dev \
    2>&1 | tail -5

  log "Системные пакеты установлены"
}

# ---------------------------------------------------------------------------
# 2. NVIDIA drivers + CUDA (for RTX 5060)
# ---------------------------------------------------------------------------
install_nvidia() {
  log "Проверка NVIDIA драйверов..."

  if command -v nvidia-smi &>/dev/null; then
    local driver_ver
    driver_ver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    log "NVIDIA драйвер уже установлен: v$driver_ver"
    log "CUDA: $(nvcc --version 2>/dev/null | grep -oP 'release \K[\d.]+' || echo 'не найдена')"
    return 0
  fi

  warn "NVIDIA драйвер НЕ найден. Установка..."
  warn "Это может занять 5-10 минут и потребует перезагрузки."

  # Add NVIDIA repo
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    local ubuntu_id
    ubuntu_id=$(echo "$VERSION_ID" | cut -d. -f1)
  else
    fail "Не удалось определить версию Ubuntu."
  fi

  # RTX 5060 (Blackwell) requires driver 570+. Use ubuntu-drivers or manual install.
  sudo apt-get install -y -qq ubuntu-drivers-common 2>&1 | tail -2
  sudo ubuntu-drivers autoinstall 2>&1 | tail -5 || warn "Автоустановка драйверов не удалась. Установите вручную: sudo apt install nvidia-driver-570"

  # CUDA toolkit (needed for llama.cpp/Ollama GPU support)
  warn "CUDA toolkit не будет установлен автоматически."
  warn "Ollama включает свои CUDA-библиотеки."
  warn "После установки драйверов ПЕРЕЗАГРУЗИТЕ компьютер."
}

# ---------------------------------------------------------------------------
# 3. Ollama (LLM inference)
# ---------------------------------------------------------------------------
install_ollama() {
  log "Установка Ollama..."

  if command -v ollama &>/dev/null; then
    log "Ollama уже установлен: $(ollama --version 2>/dev/null || echo '?')"
  else
    curl -fsSL https://ollama.com/install.sh | sh
    log "Ollama установлен"
  fi

  # Enable GPU acceleration
  if command -v nvidia-smi &>/dev/null; then
    log "NVIDIA GPU доступна — Ollama будет использовать CUDA"
  else
    warn "NVIDIA GPU недоступна — Ollama будет работать на CPU (медленно)"
  fi

  # Start Ollama service
  if systemctl is-active --quiet ollama 2>/dev/null; then
    log "Ollama сервис запущен"
  else
    log "Запуск Ollama сервиса..."
    sudo systemctl enable ollama 2>/dev/null || true
    sudo systemctl start ollama 2>/dev/null || \
      warn "Не удалось запустить Ollama как сервис. Запустите вручную: ollama serve"
  fi

  sleep 2

  # Pull models for RTX 5060 8GB
  pull_models
}

pull_models() {
  log "Загрузка моделей для RTX 5060 8GB..."

  # --- Модели, подобранные под 8GB VRAM ---
  #
  # Стратегия для RTX 5060 8GB:
  #   - Gemma 3 12B q4_K_M (~7.5GB VRAM) — основной агент (ПТО, Юрист, Сметчик, Закупщик, Логист)
  #   - Gemma 3 12B q4_K_M — PM оркестратор (та же модель для экономии VRAM)
  #   - Gemma 3 4B q4_K_M (~2.5GB VRAM) — Делопроизводитель (лёгкий)
  #   - bge-m3 (0.6GB, CPU) — Embeddings
  #   - minicpm-v (3.5GB) — Vision (опционально)
  #
  # При 8GB VRAM:
  #   - Gemma 3 12B q4_K_M: ~7.5GB с контекстом 32K → помещается
  #   - Gemma 3 4B: ~2.5GB → загружается параллельно при необходимости
  #   - bge-m3: на CPU (~1GB RAM)

  local models_to_pull=(
    "gemma3:12b"        # Основной агент (~7.5GB VRAM, 32K контекст)
    "gemma3:4b"          # Делопроизводитель (~2.5GB VRAM)
    "bge-m3:latest"      # Embeddings (CPU, ~0.6GB)
  )

  for model in "${models_to_pull[@]}"; do
    local model_name="${model%:*}"
    local model_tag="${model##*:}"
    if ollama list 2>/dev/null | grep -q "^${model_name}[[:space:]:]"; then
      # Already pulled — check tag matches
      if ollama list 2>/dev/null | grep -q "^${model_name}[[:space:]]*${model_tag}"; then
        info "  $model — уже загружена"
      else
        log "  $model — другая версия, обновляем..."
        ollama pull "$model" || warn "  Не удалось загрузить $model"
      fi
    else
      log "  Загрузка $model..."
      ollama pull "$model" || warn "  Не удалось загрузить $model"
    fi
  done

  # Опционально: minicpm-v для vision analysis
  if ollama list 2>/dev/null | grep -q "minicpm-v"; then
    info "  minicpm-v — уже загружена (vision)"
  else
    log "  Загрузка minicpm-v (vision, опционально)..."
    ollama pull "minicpm-v:latest" 2>/dev/null || \
      warn "  minicpm-v не загружена (vision будет недоступна)"
  fi

  log "Модели загружены. Проверка:"
  ollama list 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# 4. Docker + PostgreSQL
# ---------------------------------------------------------------------------
install_docker() {
  log "Установка Docker..."

  if command -v docker &>/dev/null; then
    log "Docker уже установлен: $(docker --version)"
  else
    # Add Docker's official GPG key and repo
    sudo install -m 0755 -d /etc/apt/keyrings 2>/dev/null || true
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1 | tail -5
    sudo usermod -aG docker "$USER"
    log "Docker установлен. Выйдите и зайдите заново для прав docker без sudo."
  fi

  # Install NVIDIA Container Toolkit for GPU access from Docker
  if command -v nvidia-smi &>/dev/null; then
    log "Установка NVIDIA Container Toolkit..."
    if ! dpkg -l | grep -q nvidia-container-toolkit; then
      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null || true
      curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
      sudo apt-get update -qq
      sudo apt-get install -y -qq nvidia-container-toolkit 2>&1 | tail -3
      sudo nvidia-ctk runtime configure --runtime=docker 2>/dev/null || true
      sudo systemctl restart docker 2>/dev/null || true
      log "NVIDIA Container Toolkit установлен"
    else
      log "NVIDIA Container Toolkit уже установлен"
    fi
  fi
}

start_postgres() {
  log "Запуск PostgreSQL через Docker Compose..."
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local compose_file="$script_dir/docker-compose.yml"

  if [ ! -f "$compose_file" ]; then
    fail "docker-compose.yml не найден в $script_dir"
  fi

  cd "$script_dir"
  docker compose -f "$compose_file" up -d

  log "Ожидание PostgreSQL..."
  for i in $(seq 1 15); do
    if docker compose -f "$compose_file" exec -T postgres pg_isready -U oleg -d asd_db 2>/dev/null; then
      log "PostgreSQL готов (localhost:5433)"
      return 0
    fi
    sleep 2
  done
  warn "PostgreSQL не ответил. Проверьте: docker compose -f $compose_file ps"
}

# ---------------------------------------------------------------------------
# 5. Python environment
# ---------------------------------------------------------------------------
setup_python_env() {
  log "Настройка Python окружения..."

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local project_dir="$script_dir/.."

  cd "$project_dir"

  # Create venv if not exists
  if [ -d ".venv" ]; then
    log "Виртуальное окружение .venv уже существует"
  else
    python3 -m venv .venv
    log "Создано .venv"
  fi

  # Activate and install
  source .venv/bin/activate

  log "Установка Python зависимостей..."
  pip install --upgrade pip -q

  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt 2>&1 | tail -5
  elif [ -f "pyproject.toml" ]; then
    pip install -e ".[dev]" 2>&1 | tail -5
  fi

  log "Python окружение готово"
}

# ---------------------------------------------------------------------------
# 6. Environment file
# ---------------------------------------------------------------------------
setup_env() {
  log "Настройка .env..."

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local env_file="$script_dir/../.env"

  if [ -f "$env_file" ]; then
    log ".env уже существует"
  else
    cat > "$env_file" << 'ENVEOF'
# ASD v12.0 — Linux RTX 5060 конфигурация
ASD_PROFILE=dev_linux

# Ollama (локальный)
OLLAMA_BASE_URL=http://127.0.0.1:11434

# DeepSeek API (опционально, для разработки)
# DEEPSEEK_API_KEY=sk-...
# DEEPSEEK_BASE_URL=https://api.deepseek.com

# PostgreSQL
POSTGRES_USER=oleg
POSTGRES_PASSWORD=asd_password
POSTGRES_DB=asd_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

# RAM бюджет для текущей машины (32GB)
ASD_TOTAL_RAM_GB=32.0
RAM_BUDGET_GB=32.0

# Google Workspace (опционально)
# GOOGLE_APPLICATION_CREDENTIALS=credentials/google_service_account.json
ENVEOF
    log ".env создан с настройками для RTX 5060"
  fi
}

# ---------------------------------------------------------------------------
# 7. Database initialization
# ---------------------------------------------------------------------------
init_database() {
  log "Инициализация базы данных..."

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local project_dir="$script_dir/.."

  cd "$project_dir"

  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
  fi

  # Run Alembic migrations
  if [ -f "alembic.ini" ]; then
    log "Применение миграций Alembic..."
    python -m alembic upgrade head 2>&1 | tail -5 || warn "Миграции не применены. Проверьте PostgreSQL."
  fi

  # Initialize knowledge base
  log "Инициализация knowledge base..."
  PYTHONPATH=. python -c "
from src.db.init_db import init_db
from src.core.knowledge.knowledge_base import knowledge_base
init_db()
print('Knowledge base stats:', knowledge_base.get_stats())
" 2>&1 | tail -5 || warn "Инициализация БД не удалась (возможно PostgreSQL не готов)"
}

# ---------------------------------------------------------------------------
# 8. Verify installation
# ---------------------------------------------------------------------------
verify() {
  log "=== Проверка установки ==="

  local ok=0
  local fail_count=0

  check() {
    if eval "$1" &>/dev/null; then
      info "  OK: $2"
    else
      warn "  FAIL: $2"
      ((fail_count++)) || true
    fi
  }

  check "python3 --version" "Python 3"
  check "ollama --version" "Ollama"
  check "docker --version" "Docker"
  check "docker compose version" "Docker Compose"
  check "command -v tesseract" "Tesseract OCR"

  if command -v nvidia-smi &>/dev/null; then
    local vram
    vram=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    info "  GPU VRAM: $vram"
  else
    warn "  NVIDIA GPU не обнаружена"
  fi

  # Check Ollama models
  info "  Ollama models:"
  ollama list 2>/dev/null | tail -n +2 | while read -r line; do
    info "    $line"
  done

  # Check PostgreSQL
  if docker compose -f "$(dirname "${BASH_SOURCE[0]}")/docker-compose.yml" ps 2>/dev/null | grep -q "Up"; then
    info "  PostgreSQL: running"
  else
    warn "  PostgreSQL: not running"
  fi

  echo ""
  if [ $fail_count -eq 0 ]; then
    log "=== Все проверки пройдены ==="
  else
    warn "=== $fail_count проверок не пройдено ==="
  fi

  echo ""
  log "Следующие шаги:"
  log "  1. source .venv/bin/activate"
  log "  2. Проверка: python -m src.main --mode lot_search"
  log "  3. MCP сервер: python -m mcp_servers.asd_core.server"
  log "  4. PostgreSQL: localhost:5433 (oleg / asd_password)"
  log "  5. Ollama: http://localhost:11434"
  echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  detect_system
  echo ""

  install_system_packages
  echo ""

  install_nvidia
  echo ""

  install_ollama
  echo ""

  install_docker
  echo ""

  start_postgres
  echo ""

  setup_python_env
  echo ""

  setup_env
  echo ""

  init_database
  echo ""

  verify
}

# Запуск
if [ "${1:-}" = "--verify-only" ]; then
  verify
  exit 0
fi

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "ASD v12.0 Linux Setup"
  echo "Usage: ./setup_linux.sh [--verify-only] [--help]"
  echo ""
  echo "  --verify-only  Только проверка установки"
  echo "  --help         Эта справка"
  exit 0
fi

main "$@"
