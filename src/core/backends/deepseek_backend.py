"""
ASD v12.0 — DeepSeek Backend (temporary dev bridge).

OpenAI-compatible HTTP client to DeepSeek API.
Used during development until Mac Studio + Llama/Gemma arrive.

DeepSeek API docs: https://platform.deepseek.com/api-docs
Base URL: https://api.deepseek.com
Models: deepseek-chat (V3), deepseek-reasoner (R1)

Usage:
    export ASD_PROFILE=deepseek
    export DEEPSEEK_API_KEY=sk-...
    python -m src.main
"""

import json
import logging
from typing import List, Dict, Any, Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class DeepSeekBackend:
    """
    DeepSeek API backend (OpenAI-compatible).

    Covers all LLM calls except vision (DeepSeek doesn't support vision).
    Embeddings fall back to Ollama (bge-m3).
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = (base_url or settings.DEEPSEEK_BASE_URL).rstrip("/")
        self.default_timeout = 300.0  # 5 min for long responses

        if not self.api_key:
            logger.warning(
                "DEEPSEEK_API_KEY not set. DeepSeekBackend will fail. "
                "Set it via environment variable or .env file."
            )

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
        Chat completion via DeepSeek API (OpenAI-compatible).

        Args:
            model: DeepSeek model name (e.g. "deepseek-chat")
            messages: List of {"role": "...", "content": "..."}
            temperature: Sampling temperature
            num_ctx: Max tokens for completion (maps to max_tokens)
            stream: Enable streaming
            keep_alive: Ignored (cloud API, no persistent sessions)

        Returns:
            Assistant response text
        """
        url = f"{self.base_url}/v1/chat/completions"
        logger.info(f"DeepSeek API CALL: model={model}, msgs={len(messages)}")

        is_reasoner = "reasoner" in model

        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if not is_reasoner:
            payload["temperature"] = temperature
            payload["max_tokens"] = min(num_ctx, 8192)
        else:
            # deepseek-reasoner uses max_completion_tokens, not max_tokens
            payload["max_completion_tokens"] = min(num_ctx, 8192)

        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            if not stream:
                response = await client.post(url, json=payload, headers=self._headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                chunks = []
                async for chunk_text in self._stream_response(client, url, payload):
                    chunks.append(chunk_text)
                return "".join(chunks)

    async def chat_raw(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        num_ctx: int = 32768,
        keep_alive: str = "5m",
    ) -> Dict[str, Any]:
        """
        Chat completion returning raw API response dict.
        Used for backward compatibility with code expecting Ollama JSON format.
        """
        url = f"{self.base_url}/v1/chat/completions"
        logger.info(f"DeepSeek API CALL (raw): model={model}")

        is_reasoner = "reasoner" in model

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if not is_reasoner:
            payload["temperature"] = temperature
            payload["max_tokens"] = min(num_ctx, 8192)
        else:
            payload["max_completion_tokens"] = min(num_ctx, 8192)

        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def _stream_response(
        self, client: httpx.AsyncClient, url: str, payload: Dict[str, Any]
    ):
        """Stream chat response chunks (SSE format)."""
        async with client.stream("POST", url, json=payload, headers=self._headers) as response:
            async for line in response.aiter_lines():
                if line and line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def embed(
        self,
        text: str,
        model: str = "bge-m3",
        keep_alive: str = "5m",
    ) -> List[float]:
        """
        Get text embedding vector.

        DeepSeek does NOT provide embeddings. Falls back to Ollama (bge-m3).
        This is transparent — callers don't need to know.
        """
        logger.debug("DeepSeek: embed() → delegating to Ollama (bge-m3)")
        from src.core.backends.ollama_backend import OllamaBackend

        return await OllamaBackend().embed(text=text, model=model, keep_alive=keep_alive)

    async def vision(
        self,
        image_base64: str,
        prompt: str,
        model: str = "deepseek-chat",
        temperature: float = 0.1,
        keep_alive: str = "5m",
    ) -> str:
        """
        Vision analysis — NOT SUPPORTED by DeepSeek API.

        TODO: Implement via text description fallback or use Ollama minicpm-v.
        For now, raises NotImplementedError — vision is tech debt (see #vision-fallback).
        """
        raise NotImplementedError(
            "DeepSeek API does not support vision. "
            "Use OllamaBackend with minicpm-v for vision tasks, "
            "or set ASD_PROFILE=dev_linux for vision-dependent agents."
        )

    async def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: int = 0,
    ) -> Dict[str, Any]:
        """
        Low-level generate endpoint.

        Maps to /v1/completions (legacy completion, not chat).
        keep_alive is ignored (cloud API, stateless).
        """
        url = f"{self.base_url}/v1/completions"
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": 256,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()
            return response.json()
