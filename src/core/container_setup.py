"""
ASD v12.0 — Container bootstrap wiring.

Single bootstrap() function that wires all infrastructure services
(RamManager, ModelRequestQueue, LLMEngine) and agent services into
the DI container.

Called once at application startup. After bootstrap, any code can
resolve services via container.resolve(Type).
"""
from __future__ import annotations

import logging
from typing import Any

from src.config import settings, PROFILE_MODELS
from src.core.container import container

logger = logging.getLogger(__name__)


def bootstrap() -> None:
    """Wire all core services into the DI container."""

    # ── 1. RamManager (existing singleton) ──────────────────────────
    from src.core.ram_manager import RamManager, ram_manager as _ram_mgr
    container.register_instance(RamManager, _ram_mgr)
    logger.info("Registered: RamManager")

    # ── 2. ModelRequestQueue ────────────────────────────────────────
    from src.core.model_queue import ModelRequestQueue

    _queue = ModelRequestQueue(
        default_max_concurrent=2,
        default_queue_size=100,
    )
    _queue.set_ram_manager(_ram_mgr)
    _configure_model_queue(_queue)
    container.register_instance(ModelRequestQueue, _queue)
    logger.info("Registered: ModelRequestQueue")

    # ── 3. LLMEngine (with queue) ───────────────────────────────────
    from src.core.llm_engine import LLMEngine

    _engine = LLMEngine(model_queue=_queue)
    container.register_instance(LLMEngine, _engine)
    logger.info("Registered: LLMEngine")

    # ── 4. Agent services (lazy) ────────────────────────────────────
    _register_agent_services()

    # ── 5. Support services (lazy) ──────────────────────────────────
    _register_support_services()

    container._initialized = True
    logger.info(
        "Container bootstrapped: %d registered types",
        len(container._factories) + len(container._registry),
    )


def _configure_model_queue(queue: Any) -> None:
    """Configure per-model concurrency limits from the active profile."""
    profile_models = PROFILE_MODELS.get(settings.ASD_PROFILE, {})

    seen_models: set[str] = set()
    for agent, config in profile_models.items():
        model = config["model"]
        if model in seen_models:
            continue
        seen_models.add(model)

        engine = config.get("engine", "ollama")
        if engine in ("mlx", "mlx-vlm"):
            # MLX models are not thread-safe in-process
            max_conc = 1
        elif engine == "deepseek":
            # DeepSeek API allows moderate concurrency
            max_conc = 3
        else:
            # Ollama can handle a few concurrent requests
            max_conc = 2

        queue.configure_model(model, max_concurrent=max_conc, queue_size=50)


def _register_agent_services() -> None:
    """Register agent services as lazy singletons."""
    from src.core.llm_engine import LLMEngine

    try:
        from src.core.services.legal_service import LegalService
        container.register(LegalService, lambda: LegalService(
            llm_engine=container.resolve(LLMEngine)
        ))
    except ImportError:
        pass

    try:
        from src.core.services.pto_agent import PTOAgent
        container.register(PTOAgent, lambda: PTOAgent(
            llm_engine=container.resolve(LLMEngine)
        ))
    except ImportError:
        pass

    try:
        from src.core.services.smeta_agent import SmetaAgent
        container.register(SmetaAgent, lambda: SmetaAgent(
            llm_engine=container.resolve(LLMEngine)
        ))
    except ImportError:
        pass

    try:
        from src.core.services.delo_agent import DeloAgent
        container.register(DeloAgent, lambda: DeloAgent(
            llm_engine=container.resolve(LLMEngine)
        ))
    except ImportError:
        pass


def _register_support_services() -> None:
    """Register support services as lazy singletons."""
    from src.core.llm_engine import LLMEngine

    try:
        from src.core.lessons_service import LessonsService
        container.register(LessonsService, lambda: LessonsService())
    except ImportError:
        pass

    try:
        from src.core.reference_service import ReferenceService
        container.register(ReferenceService, lambda: ReferenceService())
    except ImportError:
        pass

    try:
        from src.core.graph_service import GraphService
        container.register(GraphService, lambda: GraphService())
    except ImportError:
        pass
