"""
ASD v13.0 — Lightweight DI container.

Type-keyed service registry with lazy singleton creation, test overrides,
and full reset support. Replaces ad-hoc module-level singleton wiring.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ServiceNotRegisteredError(Exception):
    """Raised when resolving a service type that was never registered."""
    pass


class ServiceContainer:
    """
    Lightweight service container for ASD v13.0 singletons.

    Features:
      - Lazy singleton creation via factory functions
      - Eager registration of pre-built instances
      - Test override support via container.override()
      - Full reset for clean test state

    Lifecycle:
      1. Boot: register() or register_instance() for each service
      2. Runtime: resolve() returns the singleton (creates lazily)
      3. Test: override() injects mocks; reset_overrides() cleans up
    """

    def __init__(self) -> None:
        self._registry: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._overrides: dict[type, Any] = {}
        self._initialized: bool = False

    # ── Registration ─────────────────────────────────────────────────

    def register(self, service_type: type, factory: Callable[[], Any]) -> None:
        """
        Register a lazily-created singleton. The factory is called
        exactly once, on the first resolve(service_type).

        Example:
            container.register(LLMEngine, lambda: LLMEngine())
        """
        if service_type in self._factories or service_type in self._registry:
            logger.warning("Service %s already registered; replacing.", service_type.__name__)
        self._factories[service_type] = factory

    def register_instance(self, service_type: type, instance: Any) -> None:
        """
        Register an already-constructed instance (eager).

        Used for services that must exist before others, or for the
        container itself.
        """
        self._registry[service_type] = instance

    # ── Resolution ───────────────────────────────────────────────────

    def resolve(self, service_type: type[T]) -> T:
        """
        Resolve a service. On first call for a lazily-registered type,
        calls the factory, caches the result, and returns it.

        Raises ServiceNotRegisteredError if type is unknown.
        """
        # Test overrides checked first
        if service_type in self._overrides:
            return self._overrides[service_type]

        # Already built?
        if service_type in self._registry:
            return self._registry[service_type]

        # Lazy creation
        factory = self._factories.get(service_type)
        if factory is None:
            known = [t.__name__ for t in list(self._factories) + list(self._registry)]
            raise ServiceNotRegisteredError(
                f"Service '{service_type.__name__}' is not registered. "
                f"Known types: {known}"
            )

        instance = factory()
        self._registry[service_type] = instance
        logger.debug("Lazily created service: %s", service_type.__name__)
        return instance

    # ── Test support ─────────────────────────────────────────────────

    def override(self, service_type: type, instance: Any) -> None:
        """
        Override a service with a mock or stub for testing.

        Only affects future resolve() calls; does NOT affect
        already-resolved instances cached elsewhere.
        """
        self._overrides[service_type] = instance

    def reset_overrides(self) -> None:
        """Clear all test overrides (call in test teardown)."""
        self._overrides.clear()

    def reset(self) -> None:
        """
        Full reset: clear registry, factories, and overrides.
        Used in test suites that need a clean container between tests.
        """
        self._registry.clear()
        self._factories.clear()
        self._overrides.clear()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def mark_initialized(self) -> None:
        """Mark container as bootstrapped (called by container_setup)."""
        self._initialized = True


# ── Module-level singleton ────────────────────────────────────────────────

container = ServiceContainer()
