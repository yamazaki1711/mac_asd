"""
ASD v12.0 — LLM Backends.

OllamaBackend     — HTTP client to Ollama API (works on any machine)
MLXBackend        — Apple MLX in-process (Mac Studio M4 Max only)
DeepSeekBackend   — DeepSeek API (OpenAI-compatible, dev bridge)
"""

from src.core.backends.ollama_backend import OllamaBackend
from src.core.backends.mlx_backend import MLXBackend
from src.core.backends.deepseek_backend import DeepSeekBackend

__all__ = ["OllamaBackend", "MLXBackend", "DeepSeekBackend"]
