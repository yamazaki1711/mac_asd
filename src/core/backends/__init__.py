"""
ASD v11.3 — LLM Backends.

OllamaBackend  — HTTP client to Ollama API (works on any machine)
MLXBackend    — Apple MLX in-process (Mac Studio M4 Max only)
"""

from src.core.backends.ollama_backend import OllamaBackend
from src.core.backends.mlx_backend import MLXBackend

__all__ = ["OllamaBackend", "MLXBackend"]
