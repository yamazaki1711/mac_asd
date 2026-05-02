"""
src/core — ASD v12.0 core services.

Facade re-exports for centralized access to infrastructure singletons.
"""
from src.core.container import container, ServiceContainer
from src.core.model_queue import ModelRequestQueue, RequestPriority
