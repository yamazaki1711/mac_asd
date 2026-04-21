"""
ASD v11.3 — MLX Backend (Apple Silicon).

In-process LLM inference via Apple MLX framework.
Only available on Mac Studio M4 Max with macOS.

When Mac Studio arrives:
    pip install mlx-lm

This backend provides:
  - Faster inference than Ollama (no HTTP overhead)
  - Shared memory between agents (Qwen shared model)
  - Native Metal GPU acceleration
  - Direct model weight access

Status: STUB — will be implemented when Mac Studio is delivered.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MLXBackend:
    """
    Apple MLX backend for local LLM inference.

    Currently a stub — all methods raise NotImplementedError.
    When Mac Studio arrives, this will use mlx-lm for in-process inference.
    """

    def __init__(self):
        self._loaded_models: Dict[str, Any] = {}  # model_id → model instance
        logger.info(
            "MLXBackend initialized (STUB). "
            "Will be activated when Mac Studio is connected. "
            "Falling back to OllamaBackend for all requests."
        )

    def is_available(self) -> bool:
        """Check if MLX is actually available on this machine."""
        try:
            import mlx.core  # noqa: F401
            return True
        except ImportError:
            return False

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        num_ctx: int = 32768,
        stream: bool = False,
        keep_alive: str = "5m",
    ) -> str:
        """
        Chat completion via MLX.

        TODO: Implement with mlx-lm when Mac Studio arrives.
        Expected implementation:
            from mlx_lm import load, generate
            model_obj, tokenizer = load(model)
            response = generate(model_obj, tokenizer, prompt=..., temp=temperature)
        """
        raise NotImplementedError(
            f"MLXBackend.chat() not yet implemented. "
            f"Model '{model}' requires Mac Studio with MLX. "
            f"Use ASD_PROFILE=dev_linux to fall back to Ollama."
        )

    async def chat_raw(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        num_ctx: int = 32768,
        keep_alive: str = "5m",
    ) -> Dict[str, Any]:
        """Raw chat response via MLX (stub)."""
        raise NotImplementedError(
            f"MLXBackend.chat_raw() not yet implemented. "
            f"Model '{model}' requires Mac Studio with MLX."
        )

    async def embed(
        self,
        text: str,
        model: str = "bge-m3",
        keep_alive: str = "5m",
    ) -> List[float]:
        """
        Embeddings via MLX.

        NOTE: MLX is not ideal for embeddings. OllamaBackend is preferred
        even on Mac Studio. This method exists for completeness.
        """
        raise NotImplementedError(
            "MLXBackend.embed() not implemented. "
            "Use OllamaBackend for embeddings (bge-m3 via Ollama)."
        )

    async def vision(
        self,
        image_base64: str,
        prompt: str,
        model: str = "mlx-community/gemma-4-31b-it-4bit",
        temperature: float = 0.1,
        keep_alive: str = "5m",
    ) -> str:
        """
        Vision analysis via MLX (Gemma 4 Vision).

        TODO: Implement with mlx-vlm when Mac Studio arrives.
        Expected implementation:
            from mlx_vlm import load, generate
            model_obj, processor = load(model)
            response = generate(model_obj, processor, image=image, prompt=prompt)
        """
        raise NotImplementedError(
            f"MLXBackend.vision() not yet implemented. "
            f"Vision model '{model}' requires Mac Studio with mlx-vlm."
        )

    async def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: int = 0,
    ) -> Dict[str, Any]:
        """
        Low-level generate via MLX (stub).

        On Mac Studio, models are kept in memory by default (Unified Memory).
        The keep_alive parameter is not needed — models persist until explicitly unloaded.
        """
        raise NotImplementedError(
            "MLXBackend.generate() not implemented. "
            "On Mac Studio, use RAMManager for memory management."
        )

    async def load_model(self, model_id: str) -> Any:
        """
        Pre-load a model into Unified Memory.

        On Mac Studio, models stay loaded until explicitly freed.
        This allows keeping 3 models (Llama 70B + Qwen 32B + Gemma 31B)
        in 128GB Unified Memory simultaneously.

        TODO: Implement with mlx_lm.load()
        """
        if model_id in self._loaded_models:
            logger.info(f"Model {model_id} already loaded in memory.")
            return self._loaded_models[model_id]

        raise NotImplementedError(
            f"MLX model loading not yet implemented. "
            f"Model '{model_id}' will be loadable when Mac Studio arrives."
        )

    async def unload_model(self, model_id: str) -> None:
        """
        Free model from Unified Memory.

        On Mac Studio, this is rarely needed — we have 128GB.
        But useful if running memory-intensive parallel operations.
        """
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
            logger.info(f"Model {model_id} unloaded from memory.")
        else:
            logger.warning(f"Model {model_id} not found in loaded models.")
