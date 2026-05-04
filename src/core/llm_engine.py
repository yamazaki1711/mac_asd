"""
ASD v13.0 — Unified LLM Engine.

Single entry point for all LLM operations across all agents.
Automatically selects backend (Ollama / MLX) based on profile configuration.

Usage:
    from src.core.llm_engine import llm_engine

    # Simple chat — agent name determines the model
    response = await llm_engine.chat("legal", messages)

    # Vision analysis (PTO agent)
    description = await llm_engine.vision("pto", image_base64, prompt)

    # Embeddings
    vector = await llm_engine.embed("некоторый текст")

Architecture:
    Agent Name → config.get_model_config() → {"engine": "ollama"|"mlx", "model": "..."}
                                                    ↓                    ↓
                                            OllamaBackend          MLXBackend
"""

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional

from src.config import settings
from src.core.backends.ollama_backend import OllamaBackend
from src.core.backends.mlx_backend import MLXBackend
from src.core.backends.deepseek_backend import DeepSeekBackend

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0
RETRYABLE_ERRORS = (
    "connection refused",
    "connection error",
    "timeout",
    "service unavailable",
    "too many requests",
    "rate limit",
    "internal server error",
    "server error",
    "model is loading",
)


class LLMEngine:
    """
    Unified LLM interface for ASD v12.0.

    Routes requests to the appropriate backend based on profile configuration.
    In dev_linux profile — all requests go to Ollama.
    In mac_studio profile — MLX for heavy models, Ollama for embeddings.
    """

    def __init__(self, model_queue: Optional["ModelRequestQueue"] = None):
        self._profile = settings.ASD_PROFILE
        self._ollama = OllamaBackend()
        self._mlx = MLXBackend()
        self._deepseek = DeepSeekBackend()
        self._fallback_to_ollama = True  # Always allow Ollama fallback
        self._model_queue = model_queue

        logger.info(
            f"LLMEngine initialized with profile: {self._profile}. "
            f"MLX available: {self._mlx.is_available()}. "
            f"Model queue: {'enabled' if model_queue else 'disabled'}"
        )

    def _get_backend(self, engine: str):
        """Select backend by engine name."""
        if engine == "mlx":
            if self._mlx.is_available():
                return self._mlx
            elif self._fallback_to_ollama:
                logger.warning(
                    "MLX requested but not available. Falling back to Ollama. "
                    "Install mlx-lm on Mac Studio for native inference."
                )
                return self._ollama
            else:
                raise RuntimeError("MLX backend required but not available on this machine.")
        if engine == "deepseek":
            return self._deepseek
        return self._ollama

    # -------------------------------------------------------------------------
    # Core methods
    # -------------------------------------------------------------------------

    async def chat(
        self,
        agent: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
        stream: bool = False,
        keep_alive: str = "5m",
    ) -> str:
        """
        Chat completion. Agent name determines which model to use.

        Args:
            agent: Agent name (pm, pto, smeta, legal, procurement, logistics, archive)
            messages: Chat messages [{"role": "...", "content": "..."}]
            temperature: Override default temperature (optional)
            num_ctx: Override context window size (optional)
            stream: Enable streaming
            keep_alive: How long to keep model in memory

        Returns:
            Assistant response as plain text string

        Example:
            >>> response = await llm_engine.chat("legal", [
            ...     {"role": "system", "content": "Ты строительный юрист..."},
            ...     {"role": "user", "content": "Проверь договор..."}
            ... ])
        """
        config = settings.get_model_config(agent)
        backend = self._get_backend(config["engine"])
        model = config["model"]

        # Default temperature per agent type
        if temperature is None:
            temperature = self._default_temperature(agent)

        # Default context per agent type
        if num_ctx is None:
            num_ctx = self._default_context(agent)

        logger.debug(f"[LLMEngine] chat: agent={agent}, model={model}, engine={config['engine']}")

        # Route through model queue if configured
        if self._model_queue is not None:
            from src.core.model_queue import derive_model_key
            model_key = derive_model_key(agent)
            return await self._model_queue.submit(
                agent=agent,
                model_key=model_key,
                func=backend.chat,
                model=model,
                messages=messages,
                temperature=temperature,
                num_ctx=num_ctx,
                stream=stream,
                keep_alive=keep_alive,
                priority=self._default_priority(agent),
            )

        return await backend.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            num_ctx=num_ctx,
            stream=stream,
            keep_alive=keep_alive,
        )

    async def chat_raw(
        self,
        agent: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
        keep_alive: str = "5m",
    ) -> Dict[str, Any]:
        """
        Chat completion returning raw API response dict.
        Used for backward compatibility with code that expects Ollama JSON format.
        """
        config = settings.get_model_config(agent)
        backend = self._get_backend(config["engine"])
        model = config["model"]

        if temperature is None:
            temperature = self._default_temperature(agent)
        if num_ctx is None:
            num_ctx = self._default_context(agent)

        logger.debug(f"[LLMEngine] chat_raw: agent={agent}, model={model}")

        return await backend.chat_raw(
            model=model,
            messages=messages,
            temperature=temperature,
            num_ctx=num_ctx,
            keep_alive=keep_alive,
        )

    async def vision(
        self,
        agent: str,
        image_base64: str,
        prompt: str,
        temperature: float = 0.2,
        keep_alive: str = "5m",
    ) -> str:
        """
        Vision analysis — describe/analyze an image.

        Args:
            agent: Agent name (typically "pto" for drawing analysis)
            image_base64: Base64-encoded image
            prompt: Text prompt for the model
            temperature: Sampling temperature
            keep_alive: How long to keep vision model in memory

        Returns:
            Model description/analysis of the image
        """
        config = settings.get_model_config("vision")
        backend = self._get_backend(config["engine"])
        model = config["model"]

        logger.debug(f"[LLMEngine] vision: agent={agent}, model={model}")

        return await backend.vision(
            image_base64=image_base64,
            prompt=prompt,
            model=model,
            temperature=temperature,
            keep_alive=keep_alive,
        )

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Get text embedding vector.

        Always uses Ollama (bge-m3) — MLX doesn't provide embeddings efficiently.

        Args:
            text: Text to embed
            model: Override embedding model (default: from profile config)

        Returns:
            Embedding vector as list of floats
        """
        if model is None:
            config = settings.get_model_config("embed")
            model = config["model"]

        return await self._ollama.embed(text=text, model=model)

    async def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: int = 0,
    ) -> Dict[str, Any]:
        """
        Low-level generate endpoint.
        Used by RAMManager to load/unload models.

        Note: Only works with Ollama backend. MLX manages memory differently.
        """
        return await self._ollama.generate(
            model=model,
            prompt=prompt,
            keep_alive=keep_alive,
        )

    # -------------------------------------------------------------------------
    # Safe wrapper (with fallback for dev environments)
    # -------------------------------------------------------------------------

    async def safe_chat(
        self,
        agent: str,
        messages: List[Dict[str, str]],
        fallback_response: str = '{"status": "error", "message": "LLM unavailable"}',
        **kwargs,
    ) -> str:
        """
        Chat with automatic retry and fallback if LLM is unavailable.

        Uses exponential backoff for transient errors, then returns
        fallback_response if all retries are exhausted.

        Args:
            agent: Agent name
            messages: Chat messages
            fallback_response: Text to return if LLM fails after all retries
            **kwargs: Additional args passed to chat()

        Returns:
            LLM response text, or fallback_response if all retries fail
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self.chat(agent, messages, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if error is retryable
                is_retryable = any(
                    pattern in error_str
                    for pattern in RETRYABLE_ERRORS
                )

                if not is_retryable or attempt == MAX_RETRIES - 1:
                    break

                delay = min(BASE_DELAY_SECONDS * (2 ** attempt), MAX_DELAY_SECONDS)
                logger.warning(
                    "[%s] LLM attempt %d/%d failed: %s. Retrying in %.1fs...",
                    agent, attempt + 1, MAX_RETRIES, e, delay,
                )
                await asyncio.sleep(delay)

        logger.warning(
            "[%s] LLM unavailable after %d attempts: %s. Using fallback.",
            agent, MAX_RETRIES, last_error,
        )
        return fallback_response

    # -------------------------------------------------------------------------
    # Health check
    # -------------------------------------------------------------------------

    async def health_check(self) -> Dict[str, Any]:
        """
        Проверить доступность LLM бэкендов.

        Returns:
            {"status": "ok"|"degraded"|"down", "backends": {...}}
        """
        result = {"status": "ok", "backends": {}}

        # Check Ollama
        try:
            models = await self._ollama.list_models()
            result["backends"]["ollama"] = {
                "available": True,
                "models": len(models) if models else 0,
            }
        except Exception as e:
            result["backends"]["ollama"] = {"available": False, "error": str(e)}
            result["status"] = "degraded"

        # Check MLX (always unavailable on non-Mac)
        result["backends"]["mlx"] = {
            "available": self._mlx.is_available(),
        }

        # Check DeepSeek
        try:
            if settings.DEEPSEEK_API_KEY:
                result["backends"]["deepseek"] = {"available": True}
            else:
                result["backends"]["deepseek"] = {"available": False, "error": "no API key"}
        except (AttributeError, RuntimeError) as e:
            logger.debug("DeepSeek availability check failed: %s", e)
            result["backends"]["deepseek"] = {"available": False}

        ok_count = sum(
            1 for b in result["backends"].values()
            if b.get("available", False)
        )
        if ok_count == 0:
            result["status"] = "down"

        return result

    # -------------------------------------------------------------------------
    # Defaults per agent
    # -------------------------------------------------------------------------

    @staticmethod
    def _default_priority(agent: str) -> "RequestPriority":
        """Default queue priority per agent role."""
        from src.core.model_queue import RequestPriority
        priorities = {
            "pm": RequestPriority.CRITICAL,
            "legal": RequestPriority.HIGH,
            "smeta": RequestPriority.HIGH,
            "pto": RequestPriority.NORMAL,
            "procurement": RequestPriority.NORMAL,
            "archive": RequestPriority.NORMAL,
            "logistics": RequestPriority.LOW,
        }
        return priorities.get(agent, RequestPriority.NORMAL)

    @staticmethod
    def _default_temperature(agent: str) -> float:
        """Default temperature per agent role."""
        temps = {
            "pm": 0.3,
            "pto": 0.2,
            "smeta": 0.1,
            "legal": 0.1,
            "procurement": 0.2,
            "logistics": 0.2,
            "archive": 0.1,
        }
        return temps.get(agent, 0.2)

    @staticmethod
    def _default_context(agent: str) -> int:
        """
        Default context window size per agent role.

        v12.0: Gemma 4 31B (PTO/Legal/Smeta) → 128K context.
        Эти агенты делят одну модель и используют полный 128K контекст,
        что позволяет анализировать длинные договоры без Map-Reduce.

        Контекст берётся из asd_manifest.yaml (context_tokens).
        Эти дефолты — fallback если манифест недоступен.
        """
        contexts = {
            "pm": 131072,      # Llama 3.3 70B — 128K контекст
            "pto": 131072,     # Gemma 4 31B — 128K контекст (vision + text)
            "smeta": 131072,   # Gemma 4 31B — 128K контекст (shared с ПТО)
            "legal": 131072,   # Gemma 4 31B — 128K контекст (shared с ПТО)
            "procurement": 131072,  # Gemma 4 31B — 128K контекст (shared с ПТО)
            "logistics": 131072,    # Gemma 4 31B — 128K контекст (shared с ПТО)
            "archive": 8192,       # Gemma 4 E4B — 8K (регистрация)
        }
        return contexts.get(agent, 16384)


# Global singleton
llm_engine = LLMEngine()
