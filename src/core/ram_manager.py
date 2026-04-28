"""
ASD v12.0 — RAM Manager.

Мониторинг и защита памяти для Mac Studio M4 Max 128GB.
Архитектура shared-memory (Gemma 4 31B обслуживает 5 агентов) требует
жёсткого контроля потребления RAM, чтобы избежать OOM.

Уровни защиты:
  1. Мониторинг — отслеживание текущего потребления через psutil
  2. Квоты — лимиты на агентов (контекст, модель)
  3. OOM-защита — блокировка новых задач при приближении к лимиту
  4. Деградация — автоматический сброс кэша, уменьшение контекста

Бюджет памяти (из MODEL_STRATEGY.md):
  Llama 3.3 70B 4-bit    ~40 GB   (PM)
  Gemma 4 31B 4-bit      ~23 GB   (5 agents shared)
  Gemma 4 E4B 4-bit       ~3 GB   (Делопроизводитель)
  bge-m3-mlx-4bit         ~0.3 GB (Embeddings)
  macOS + системные        ~8 GB
  PostgreSQL 16            ~2 GB
  MLX runtime              ~6 GB
  Python (MCP + LightRAG)  ~4 GB
  ─────────────────────────────
  ИТОГО базовое           ~86 GB  (при полной загрузке моделей)
  Свободно                ~42 GB  (из 128 GB)

Пороги:
  NORMAL:     < 80 GB  — свободный режим
  WARNING:    80-90 GB — мониторинг, предупреждения
  CRITICAL:   90-100 GB — блокировка новых тяжёлых задач
  OOM_DANGER: > 100 GB — сброс кэша, деградация, аварийная остановка

Usage:
    from src.core.ram_manager import ram_manager

    if ram_manager.can_accept_task("pto", context_size=10000):
        # OK to process
        pass
    else:
        # Reject or queue
        pass
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Constants — Memory Budget (from MODEL_STRATEGY.md)
# =============================================================================

# Бюджет загрузки моделей (только сами веса, без контекста)
MODEL_WEIGHTS_BUDGET: Dict[str, float] = {
    "pm":          40.0,   # Llama 3.3 70B 4-bit
    "pto":          0.0,   # Shared (учтён в gemma_31b)
    "legal":        0.0,   # Shared
    "smeta":        0.0,   # Shared
    "procurement":  0.0,   # Shared
    "logistics":    0.0,   # Shared
    "gemma_31b":   23.0,   # Gemma 4 31B 4-bit (shared by 5 agents)
    "archive":      3.0,   # Gemma 4 E4B 4-bit
    "embed":        0.3,   # bge-m3-mlx-4bit
}

# Базовая системная нагрузка (OS, Postgres, MLX runtime, Python)
BASE_SYSTEM_RAM = 20.0  # GB

# Пороги памяти (GB used)
NORMAL_THRESHOLD = 80.0
WARNING_THRESHOLD = 90.0
CRITICAL_THRESHOLD = 100.0
OOM_DANGER_THRESHOLD = 110.0  # Аварийный порог

# Коэффициент контекста: ~0.5 GB на 1K токенов для Gemma 4 31B (приблизительно)
CONTEXT_RAM_PER_1K_TOKENS = 0.0005  # GB


# =============================================================================
# Enums
# =============================================================================

class RamStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    OOM_DANGER = "oom_danger"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RamSnapshot:
    """Снимок состояния памяти на момент измерения."""
    total_gb: float
    used_gb: float
    available_gb: float
    percent_used: float
    status: RamStatus
    timestamp: str
    process_rss_gb: float = 0.0
    python_objects_mb: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "total_gb": round(self.total_gb, 2),
            "used_gb": round(self.used_gb, 2),
            "available_gb": round(self.available_gb, 2),
            "percent_used": round(self.percent_used, 1),
            "status": self.status.value,
            "timestamp": self.timestamp,
            "process_rss_gb": round(self.process_rss_gb, 2),
            "python_objects_mb": round(self.python_objects_mb, 1),
        }


@dataclass
class AgentRamQuota:
    """Квота памяти для одного агента (контекст + overhead)."""
    agent_name: str
    max_context_tokens: int = 128000
    current_tasks: int = 0
    max_concurrent_tasks: int = 1
    reserved_ram_gb: float = 0.0

    def estimated_ram_usage(self, context_tokens: int = 0) -> float:
        """Оценить потребление RAM агентом с учётом контекста."""
        base = self.reserved_ram_gb
        context_ram = context_tokens * CONTEXT_RAM_PER_1K_TOKENS / 1000
        return base + context_ram


# =============================================================================
# RAM Manager
# =============================================================================

class RamManager:
    """
    Менеджер оперативной памяти ASD v12.0.

    Отслеживает потребление RAM на уровне системы и процесса,
    управляет квотами агентов и предотвращает OOM.
    """

    def __init__(self, total_ram_gb: float = 128.0):
        self._total_ram_gb = total_ram_gb
        self._lock = threading.Lock()
        self._snapshot_interval = 5.0  # секунд между замерами
        self._last_snapshot_time = 0.0
        self._cached_snapshot: Optional[RamSnapshot] = None

        # Квоты агентов
        self._agent_quotas: Dict[str, AgentRamQuota] = {
            "pm": AgentRamQuota(
                agent_name="pm",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=40.0,
            ),
            "pto": AgentRamQuota(
                agent_name="pto",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,  # Shared model
            ),
            "legal": AgentRamQuota(
                agent_name="legal",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "smeta": AgentRamQuota(
                agent_name="smeta",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "procurement": AgentRamQuota(
                agent_name="procurement",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "logistics": AgentRamQuota(
                agent_name="logistics",
                max_context_tokens=128000,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "archive": AgentRamQuota(
                agent_name="archive",
                max_context_tokens=8000,   # Gemma 4 E4B — короткий контекст
                max_concurrent_tasks=1,
                reserved_ram_gb=3.0,
            ),
        }

        # Счётчики деградации
        self._degradation_level = 0       # 0=нет, 1=кэш, 2=контекст, 3=отказ
        self._cache_clears = 0
        self._task_rejections = 0

        logger.info(
            "RamManager initialized: %.0f GB total, thresholds: "
            "NORMAL<%.0f WARNING<%.0f CRITICAL<%.0f OOM<%.0f",
            total_ram_gb, NORMAL_THRESHOLD, WARNING_THRESHOLD,
            CRITICAL_THRESHOLD, OOM_DANGER_THRESHOLD,
        )

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    def get_snapshot(self, force: bool = False) -> RamSnapshot:
        """
        Получить текущий снимок памяти.

        Args:
            force: принудительно обновить (игнорировать кэш)

        Returns:
            RamSnapshot с текущими метриками
        """
        now = time.time()

        # Используем кэшированный снимок если интервал не истёк
        if not force and self._cached_snapshot and (now - self._last_snapshot_time) < self._snapshot_interval:
            return self._cached_snapshot

        try:
            import psutil
        except ImportError:
            logger.debug("psutil not available — RAM monitoring disabled")
            return RamSnapshot(
                total_gb=self._total_ram_gb,
                used_gb=86.0,
                available_gb=self._total_ram_gb - 86.0,
                percent_used=67.2,
                status=RamStatus.NORMAL,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )

        mem = psutil.virtual_memory()
        process = psutil.Process(os.getpid())

        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        percent_used = mem.percent
        process_rss = process.memory_info().rss / (1024 ** 3)

        # Оценка Python-объектов через gc
        try:
            gc.collect()
            python_objects_kb = sum(
                sys.getsizeof(o) for o in gc.get_objects()
                if not isinstance(o, (type, module, function))
            )
            python_objects_mb = python_objects_kb / 1024
        except Exception:
            python_objects_mb = 0.0

        # Определение статуса
        if used_gb >= OOM_DANGER_THRESHOLD:
            status = RamStatus.OOM_DANGER
        elif used_gb >= CRITICAL_THRESHOLD:
            status = RamStatus.CRITICAL
        elif used_gb >= WARNING_THRESHOLD:
            status = RamStatus.WARNING
        else:
            status = RamStatus.NORMAL

        snapshot = RamSnapshot(
            total_gb=round(total_gb, 2),
            used_gb=round(used_gb, 2),
            available_gb=round(available_gb, 2),
            percent_used=round(percent_used, 1),
            status=status,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            process_rss_gb=round(process_rss, 2),
            python_objects_mb=round(python_objects_mb, 1),
        )

        with self._lock:
            self._cached_snapshot = snapshot
            self._last_snapshot_time = now

        if status != RamStatus.NORMAL:
            logger.warning(
                "RAM %s: %.1f/%.1f GB (%.1f%%), available: %.1f GB, "
                "process RSS: %.1f GB, Python objects: %.1f MB",
                status.value, used_gb, total_gb, percent_used,
                available_gb, process_rss, python_objects_mb,
            )

        return snapshot

    # -------------------------------------------------------------------------
    # Task Acceptance
    # -------------------------------------------------------------------------

    def can_accept_task(
        self,
        agent_name: str,
        context_tokens: int = 0,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> bool:
        """
        Проверить, можно ли принять новую задачу для агента.

        Args:
            agent_name: имя агента
            context_tokens: ожидаемый размер контекста в токенах
            priority: приоритет задачи

        Returns:
            True если задача может быть принята
        """
        snapshot = self.get_snapshot()

        # Критические задачи принимаются всегда (кроме OOM_DANGER)
        if priority == TaskPriority.CRITICAL:
            if snapshot.status == RamStatus.OOM_DANGER:
                logger.error(
                    "CRITICAL task rejected for %s: OOM_DANGER (%.1f GB used)",
                    agent_name, snapshot.used_gb,
                )
                self._task_rejections += 1
                return False
            return True

        # Высокоприоритетные — только до CRITICAL
        if priority == TaskPriority.HIGH:
            if snapshot.status in (RamStatus.CRITICAL, RamStatus.OOM_DANGER):
                logger.warning(
                    "HIGH priority task rejected for %s: %s (%.1f GB used)",
                    agent_name, snapshot.status.value, snapshot.used_gb,
                )
                self._task_rejections += 1
                return False
            return True

        # Обычные и низкоприоритетные — только при NORMAL
        if snapshot.status != RamStatus.NORMAL:
            logger.info(
                "Task rejected for %s: RAM %s (%.1f GB used, %.1f GB available)",
                agent_name, snapshot.status.value, snapshot.used_gb, snapshot.available_gb,
            )
            self._task_rejections += 1
            return False

        # Проверка квоты агента
        quota = self._agent_quotas.get(agent_name)
        if quota:
            if quota.current_tasks >= quota.max_concurrent_tasks:
                logger.info(
                    "Task rejected for %s: agent quota exhausted (%d/%d tasks)",
                    agent_name, quota.current_tasks, quota.max_concurrent_tasks,
                )
                return False

            # Оценка потребления RAM с контекстом
            estimated = quota.estimated_ram_usage(context_tokens)
            if snapshot.available_gb < estimated * 1.2:  # 20% запас
                logger.warning(
                    "Task rejected for %s: insufficient RAM (need ~%.1f GB, have %.1f GB)",
                    agent_name, estimated, snapshot.available_gb,
                )
                return False

        return True

    def register_task_start(self, agent_name: str) -> None:
        """Зарегистрировать начало задачи агента."""
        quota = self._agent_quotas.get(agent_name)
        if quota:
            quota.current_tasks += 1
            logger.debug(
                "Agent %s started task (%d/%d active)",
                agent_name, quota.current_tasks, quota.max_concurrent_tasks,
            )

    def register_task_end(self, agent_name: str) -> None:
        """Зарегистрировать завершение задачи агента."""
        quota = self._agent_quotas.get(agent_name)
        if quota:
            quota.current_tasks = max(0, quota.current_tasks - 1)
            logger.debug(
                "Agent %s finished task (%d/%d active)",
                agent_name, quota.current_tasks, quota.max_concurrent_tasks,
            )

    # -------------------------------------------------------------------------
    # Degradation
    # -------------------------------------------------------------------------

    def degrade(self) -> str:
        """
        Применить следующий уровень деградации при нехватке памяти.

        Уровни:
          1 — сброс Python GC + cachetools
          2 — уменьшение контекста агентов на 50%
          3 — принудительная остановка некритичных задач

        Returns:
            Описание применённой деградации
        """
        self._degradation_level += 1
        level = self._degradation_level

        if level == 1:
            # Сброс кэша и сборка мусора
            gc.collect()
            self._cache_clears += 1
            logger.warning("RAM degradation level 1: GC collect + cache clear")
            return "level_1_gc_collect"

        elif level == 2:
            # Уменьшение контекста
            for quota in self._agent_quotas.values():
                if quota.max_context_tokens > 16000:
                    quota.max_context_tokens = max(16000, quota.max_context_tokens // 2)
            logger.warning("RAM degradation level 2: context halved for all agents")
            return "level_2_context_halved"

        elif level >= 3:
            # Принудительная остановка
            logger.error("RAM degradation level 3: emergency — reject all non-critical tasks")
            return "level_3_emergency_reject"

        return "unknown"

    def reset_degradation(self) -> None:
        """Сбросить уровень деградации (при восстановлении памяти)."""
        if self._degradation_level > 0:
            logger.info("RAM degradation reset (was level %d)", self._degradation_level)
            self._degradation_level = 0
            # Восстановить контекст
            for agent_name, quota in self._agent_quotas.items():
                if agent_name == "archive":
                    quota.max_context_tokens = 8000
                else:
                    quota.max_context_tokens = 128000

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Получить статистику RAM Manager."""
        snapshot = self.get_snapshot()
        return {
            "snapshot": snapshot.to_dict(),
            "degradation_level": self._degradation_level,
            "cache_clears": self._cache_clears,
            "task_rejections": self._task_rejections,
            "agent_quotas": {
                name: {
                    "current_tasks": q.current_tasks,
                    "max_concurrent": q.max_concurrent_tasks,
                    "max_context_tokens": q.max_context_tokens,
                    "reserved_ram_gb": q.reserved_ram_gb,
                }
                for name, q in self._agent_quotas.items()
            },
        }


# =============================================================================
# Module-level singleton
# =============================================================================

# Общий размер RAM определяется из окружения или 128 GB по умолчанию
_TOTAL_RAM_GB = float(os.environ.get("ASD_TOTAL_RAM_GB", "128.0"))

ram_manager = RamManager(total_ram_gb=_TOTAL_RAM_GB)
