"""
ASD v11.3 — Ollama Client (DEPRECATED — use llm_engine instead).

This module is kept for backward compatibility with existing code
that directly imports `ollama_client`. New code should use:

    from src.core.llm_engine import llm_engine

Migration guide:
    # OLD:
    from src.core.ollama_client import ollama_client
    response = await ollama_client.chat(messages=messages)
    text = response['message']['content']

    # NEW:
    from src.core.llm_engine import llm_engine
    text = await llm_engine.chat("legal", messages)
"""

import logging
from typing import AsyncGenerator, List, Dict, Any

from src.core.llm_engine import llm_engine
from src.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Backward-compatible Ollama client wrapper.

    Delegates all calls to LLMEngine, which routes to the appropriate backend.
    """

    def __init__(self):
        self.base_url = f"{settings.OLLAMA_BASE_URL}/api"
        self.model = settings.get_model_config("legal")["model"]  # default model
        logger.warning(
            "OllamaClient is deprecated. Use llm_engine instead. "
            "from src.core.llm_engine import llm_engine"
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        temperature: float = 0.1,
        keep_alive: str = "5m",
    ) -> Any:
        """
        Chat completion (backward compatible).
        Returns raw Ollama API response dict with response['message']['content'].
        """
        return await llm_engine.chat_raw(
            agent="legal",  # default agent
            messages=messages,
            temperature=temperature,
            keep_alive=keep_alive,
        )

    async def embeddings(self, text: str, keep_alive: str = "5m") -> List[float]:
        """Get embeddings via LLMEngine."""
        return await llm_engine.embed(text=text)

    async def get_embedding(self, text: str) -> List[float]:
        """Backward compatibility alias for embeddings()."""
        return await self.embeddings(text)

    async def generate_base(self, model: str, prompt: str, keep_alive: int = 0):
        """Low-level generate endpoint (for RAMManager)."""
        return await llm_engine.generate(
            model=model,
            prompt=prompt,
            keep_alive=keep_alive,
        )


# Singleton (backward compatible)
ollama_client = OllamaClient()
