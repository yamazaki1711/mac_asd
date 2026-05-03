"""
ASD v12.0 — Ollama Backend.

HTTP client to Ollama API. Works on any machine with Ollama installed.
Used for:
  - All LLM calls in dev_linux profile
  - Embeddings (bge-m3) in all profiles
  - Fallback in mac_studio profile
"""

import httpx
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from src.config import settings

logger = logging.getLogger(__name__)


class OllamaBackend:
    """Ollama API backend via HTTP."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = f"{base_url or settings.OLLAMA_BASE_URL}/api"
        self.default_timeout = 180.0  # 3 min for large models

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
        Chat completion. Returns assistant message content as string.

        Args:
            model: Ollama model name (e.g. "gemma4:31b-cloud")
            messages: List of {"role": "user"|"system"|"assistant", "content": "..."}
            temperature: Sampling temperature
            num_ctx: Context window size in tokens
            stream: Enable streaming
            keep_alive: How long to keep model in memory

        Returns:
            Assistant response text
        """
        url = f"{self.base_url}/chat"
        logger.debug("Ollama Backend CALL -> %s (model: %s)", url, model)
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
        }

        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            if not stream:
                response = await client.post(f"{self.base_url}/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            else:
                # Collect streaming response
                chunks = []
                async for chunk in self._stream_response(client, payload):
                    chunks.append(chunk)
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
        Chat completion. Returns raw Ollama API response dict.
        Used for backward compatibility.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
        }

        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            response = await client.post(f"{self.base_url}/chat", json=payload)
            response.raise_for_status()
            return response.json()

    async def _stream_response(
        self, client: httpx.AsyncClient, payload: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Stream chat response chunks."""
        async with client.stream("POST", f"{self.base_url}/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        break

    async def embed(
        self,
        text: str,
        model: str = "bge-m3",
        keep_alive: str = "5m",
    ) -> List[float]:
        """
        Get text embedding vector.

        Args:
            text: Text to embed
            model: Embedding model name (default: bge-m3)
            keep_alive: How long to keep model in memory

        Returns:
            Embedding vector as list of floats
        """
        payload = {
            "model": model,
            "prompt": text,
            "keep_alive": keep_alive,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}/embeddings", json=payload)
            response.raise_for_status()
            return response.json()["embedding"]

    async def vision(
        self,
        image_base64: str,
        prompt: str,
        model: str = "minicpm-v",
        temperature: float = 0.1,
        keep_alive: str = "5m",
    ) -> str:
        """
        Vision model — analyze an image.

        Args:
            image_base64: Base64-encoded image
            prompt: Text prompt for the model
            model: Vision model name
            temperature: Sampling temperature
            keep_alive: How long to keep model in memory

        Returns:
            Model response text
        """
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ]

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": 16384,
            },
        }

        async with httpx.AsyncClient(timeout=self.default_timeout) as client:
            response = await client.post(f"{self.base_url}/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")

    async def generate(
        self,
        model: str,
        prompt: str,
        keep_alive: int = 0,
    ) -> Dict[str, Any]:
        """
        Low-level generate endpoint.
        Used by RAMManager to load/unload models (keep_alive=0 → unload).

        Args:
            model: Model name
            prompt: Text prompt (empty string for unload)
            keep_alive: Time to keep model in memory (0 = unload immediately)

        Returns:
            Raw API response dict
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "keep_alive": keep_alive,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/generate", json=payload)
            response.raise_for_status()
            return response.json()

    async def list_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        List models available in Ollama.

        Returns:
            List of model dicts with name, size, etc., or None if unavailable.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/../api/tags")
                response.raise_for_status()
                data = response.json()
                return data.get("models", [])
        except Exception as e:
            logger.debug("Ollama list_models failed: %s", e)
            return None

    async def health(self) -> Dict[str, Any]:
        """
        Quick health check — tries to reach Ollama API.

        Returns:
            {"available": True/False, "error": ..., "models_count": int}
        """
        try:
            models = await self.list_models()
            if models is not None:
                return {"available": True, "models_count": len(models)}
            return {"available": False, "error": "no response"}
        except Exception as e:
            return {"available": False, "error": str(e)}
