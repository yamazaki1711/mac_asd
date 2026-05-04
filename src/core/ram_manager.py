"""
ASD v12.0 — RAM Manager.

Мониторинг и защита памяти. Поддерживает две архитектуры:
  - Apple Silicon (Mac Studio, unified memory) — 128GB
  - NVIDIA GPU (Linux, дискретная VRAM) — 8GB VRAM + системная RAM

Уровни защиты:
  1. Мониторинг — отслеживание системной RAM и GPU VRAM (nvidia-smi)
  2. Квоты — лимиты на агентов (контекст, модель)
  3. OOM-защита — блокировка новых задач при приближении к лимиту
  4. Деградация — автоматический сброс кэша, уменьшение контекста

Адаптивные пороги — вычисляются как доля от общего объёма RAM.
Для NVIDIA GPU: раздельный учёт VRAM (через nvidia-smi) и системной RAM.

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
import subprocess
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Platform Detection
# =============================================================================

def _detect_total_ram_gb() -> float:
    """Автоопределение общего объёма системной RAM."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        return float(os.environ.get("ASD_TOTAL_RAM_GB", "32.0"))


def _detect_gpu_vram_gb() -> Optional[float]:
    """Определение VRAM NVIDIA GPU через nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Convert MB to GB
            vram_mb = float(result.stdout.strip().split("\n")[0])
            return vram_mb / 1024.0
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return None


_TOTAL_RAM_GB = _detect_total_ram_gb()
_GPU_VRAM_GB = _detect_gpu_vram_gb()
_IS_APPLE_SILICON = "arm" in os.uname().machine if hasattr(os, "uname") else False


# =============================================================================
# Constants — Memory Budget (adaptive, computed from total RAM)
# =============================================================================

# Пороги как доля от общей RAM
_NORMAL_FRACTION = 0.70    # < 70% — свободный режим
_WARNING_FRACTION = 0.80   # 70-80% — мониторинг, предупреждения
_CRITICAL_FRACTION = 0.88  # 80-88% — блокировка новых тяжёлых задач
_OOM_FRACTION = 0.94       # > 88% — сброс кэша, деградация

# Вычисляемые пороги
NORMAL_THRESHOLD = _TOTAL_RAM_GB * _NORMAL_FRACTION
WARNING_THRESHOLD = _TOTAL_RAM_GB * _WARNING_FRACTION
CRITICAL_THRESHOLD = _TOTAL_RAM_GB * _CRITICAL_FRACTION
OOM_DANGER_THRESHOLD = _TOTAL_RAM_GB * _OOM_FRACTION

# Бюджет моделей — зависит от платформы
if _IS_APPLE_SILICON:
    # Mac Studio M4 Max 128GB — unified memory, все модели загружены одновременно
    MODEL_WEIGHTS_BUDGET: Dict[str, float] = {
        "pm":          40.0,   # Llama 3.3 70B 4-bit
        "pto":          0.0,   # Shared (gemma_31b)
        "legal":        0.0,   # Shared
        "smeta":        0.0,   # Shared
        "procurement":  0.0,   # Shared
        "logistics":    0.0,   # Shared
        "gemma_31b":   23.0,   # Gemma 4 31B 4-bit (shared by 5 agents)
        "archive":      3.0,   # Gemma 4 E4B 4-bit
        "embed":        0.3,   # bge-m3
    }
    BASE_SYSTEM_RAM = 20.0  # macOS + PostgreSQL + MLX + Python
else:
    # Linux RTX 5060 — одна модель в VRAM, embeddings на CPU
    _shared_model_gb = 7.5 if _GPU_VRAM_GB and _GPU_VRAM_GB >= 7.8 else 5.0
    MODEL_WEIGHTS_BUDGET: Dict[str, float] = {
        "pm":          0.0,   # Shared (та же модель что и агенты)
        "pto":          0.0,   # Shared
        "legal":        0.0,   # Shared
        "smeta":        0.0,   # Shared
        "procurement":  0.0,   # Shared
        "logistics":    0.0,   # Shared
        "gemma_12b":   _shared_model_gb,  # Gemma 3 12B q4 (все агенты, в VRAM)
        "archive":      0.0,   # Shared (та же модель)
        "embed":        1.2,   # bge-m3 (CPU, системная RAM)
    }
    BASE_SYSTEM_RAM = 5.0   # Ubuntu + PostgreSQL + Python (без MLX)

# Коэффициент контекста: ~0.5 GB на 1K токенов
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

    Отслеживает потребление RAM на уровне системы и GPU VRAM,
    управляет квотами агентов и предотвращает OOM.

    Адаптивные пороги вычисляются как доля от общего объёма RAM.
    Для NVIDIA GPU: раздельный учёт VRAM (nvidia-smi) + системной RAM.
    """

    def __init__(self, total_ram_gb: Optional[float] = None):
        self._total_ram_gb = total_ram_gb or _TOTAL_RAM_GB
        self._gpu_vram_gb = _GPU_VRAM_GB
        self._is_apple_silicon = _IS_APPLE_SILICON
        self._lock = threading.Lock()
        self._snapshot_interval = 5.0  # секунд между замерами
        self._last_snapshot_time = 0.0
        self._cached_snapshot: Optional[RamSnapshot] = None

        # Контекст адаптируется под платформу
        if self._is_apple_silicon:
            default_context = 128000
            archive_context = 8000
            pm_ram = 40.0
            archive_ram = 3.0
        else:
            # RTX 5060: Gemma 3 12B — 32K контекст (влезает в 8GB VRAM)
            default_context = 32768
            archive_context = 32768  # Та же модель что и все
            pm_ram = 0.0  # Shared model
            archive_ram = 0.0  # Shared model

        # Квоты агентов
        self._agent_quotas: Dict[str, AgentRamQuota] = {
            "pm": AgentRamQuota(
                agent_name="pm",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=pm_ram,
            ),
            "pto": AgentRamQuota(
                agent_name="pto",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,  # Shared model
            ),
            "legal": AgentRamQuota(
                agent_name="legal",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "smeta": AgentRamQuota(
                agent_name="smeta",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "procurement": AgentRamQuota(
                agent_name="procurement",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "logistics": AgentRamQuota(
                agent_name="logistics",
                max_context_tokens=default_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=0.0,
            ),
            "archive": AgentRamQuota(
                agent_name="archive",
                max_context_tokens=archive_context,
                max_concurrent_tasks=1,
                reserved_ram_gb=archive_ram,
            ),
        }

        # Счётчики деградации
        self._degradation_level = 0       # 0=нет, 1=кэш, 2=контекст, 3=отказ
        self._cache_clears = 0
        self._task_rejections = 0

        logger.info(
            "RamManager initialized: %.0f GB RAM%s, thresholds: "
            "NORMAL<%.0f WARNING<%.0f CRITICAL<%.0f OOM<%.0f",
            self._total_ram_gb,
            f" + {self._gpu_vram_gb:.0f}GB VRAM" if self._gpu_vram_gb else "",
            NORMAL_THRESHOLD, WARNING_THRESHOLD,
            CRITICAL_THRESHOLD, OOM_DANGER_THRESHOLD,
        )

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    def get_snapshot(self, force: bool = False) -> RamSnapshot:
        """
        Получить текущий снимок памяти.

        Для NVIDIA GPU дополнительно отслеживает VRAM через nvidia-smi.

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
                used_gb=0.0,
                available_gb=self._total_ram_gb,
                percent_used=0.0,
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

        # GPU VRAM через nvidia-smi
        gpu_used_gb = 0.0
        gpu_total_gb = 0.0
        if self._gpu_vram_gb:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split(",")
                    gpu_used_gb = float(parts[0].strip()) / 1024.0
                    gpu_total_gb = float(parts[1].strip()) / 1024.0
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
                pass

        # Оценка Python-объектов через gc
        try:
            gc.collect()
            python_objects_kb = sum(
                sys.getsizeof(o) for o in gc.get_objects()
                if not isinstance(o, (type, types.ModuleType)) and not callable(o)
            )
            python_objects_mb = python_objects_kb / 1024
        except (TypeError, RuntimeError, OSError) as e:
            logger.debug("Failed to estimate Python object memory: %s", e)
            python_objects_mb = 0.0

        # Определение статуса (с учётом GPU если есть)
        if self._gpu_vram_gb and gpu_total_gb > 0:
            # Если GPU VRAM заполнена — CRITICAL даже при свободной RAM
            gpu_pct = gpu_used_gb / gpu_total_gb * 100 if gpu_total_gb > 0 else 0
            if gpu_pct > 95:
                status = RamStatus.CRITICAL
            elif used_gb >= OOM_DANGER_THRESHOLD:
                status = RamStatus.OOM_DANGER
            elif used_gb >= CRITICAL_THRESHOLD:
                status = RamStatus.CRITICAL
            elif used_gb >= WARNING_THRESHOLD:
                status = RamStatus.WARNING
            else:
                status = RamStatus.NORMAL
        else:
            if used_gb >= OOM_DANGER_THRESHOLD:
                status = RamStatus.OOM_DANGER
            elif used_gb >= CRITICAL_THRESHOLD:
                status = RamStatus.CRITICAL
            elif used_gb >= WARNING_THRESHOLD:
                status = RamStatus.WARNING
            elif used_gb >= NORMAL_THRESHOLD:
                status = RamStatus.WARNING  # elevated — treat as warning on constrained hardware
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
            gpu_info = f", GPU: {gpu_used_gb:.1f}/{gpu_total_gb:.1f}GB" if gpu_total_gb > 0 else ""
            logger.warning(
                "RAM %s: %.1f/%.1f GB (%.1f%%), available: %.1f GB, "
                "process RSS: %.1f GB, Python objects: %.1f MB%s",
                status.value, used_gb, total_gb, percent_used,
                available_gb, process_rss, python_objects_mb, gpu_info,
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

            # Восстановить контекст под платформу
            if self._is_apple_silicon:
                default_ctx, archive_ctx = 128000, 8000
            else:
                default_ctx, archive_ctx = 32768, 32768

            for agent_name, quota in self._agent_quotas.items():
                quota.max_context_tokens = archive_ctx if agent_name == "archive" and self._is_apple_silicon else default_ctx

    # -------------------------------------------------------------------------
    # GPU Memory
    # -------------------------------------------------------------------------

    def get_gpu_memory_used_gb(self) -> Optional[float]:
        """Возвращает использованную VRAM в GB (NVIDIA GPU) или None."""
        if not self._gpu_vram_gb:
            return None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip()) / 1024.0
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        return None

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Получить статистику RAM Manager."""
        snapshot = self.get_snapshot()
        stats = {
            "snapshot": snapshot.to_dict(),
            "platform": {
                "is_apple_silicon": self._is_apple_silicon,
                "total_ram_gb": self._total_ram_gb,
                "gpu_vram_gb": self._gpu_vram_gb,
            },
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
        gpu_used = self.get_gpu_memory_used_gb()
        if gpu_used is not None:
            stats["gpu"] = {
                "vram_used_gb": round(gpu_used, 2),
                "vram_total_gb": self._gpu_vram_gb,
                "vram_free_gb": round(self._gpu_vram_gb - gpu_used, 2),
            }
        return stats


# =============================================================================
# Module-level singleton
# =============================================================================

ram_manager = RamManager(total_ram_gb=_TOTAL_RAM_GB)
