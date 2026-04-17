import httpx
import json
import logging
from typing import AsyncGenerator, List, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self):
        self.base_url = f"{settings.OLLAMA_BASE_URL}/api"
        self.model = settings.PRIMARY_MODEL

    async def chat(self, messages: List[Dict[str, str]], stream: bool = False, temperature: float = 0.1, keep_alive: str = "5m") -> Any:
        """
        Основной метод для общения с Gemma 4.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,  # Для точности в сметах и законах
                "num_ctx": 32768,    # Хороший контекст для длинных PDF
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            if not stream:
                response = await client.post(f"{self.base_url}/chat", json=payload)
                response.raise_for_status()
                # Returns nested dict depending on caller structure, let's return raw json or message content
                # To be compatible with nodes.py passing json.loads(), we will return response.json()["message"]["content"] directly or raw if needed.
                # Nodes expects raw API response because it does `response["message"]["content"]` actually ? Wait, in nodes we did `response = await ollama_client...` 
                # Let's keep it returning the `.json()` dict to not break backwards compatibility if possible.
                return response.json()
            else:
                return self._stream_response(client, payload)

    async def _stream_response(self, client, payload) -> AsyncGenerator[str, None]:
        async with client.stream("POST", f"{self.base_url}/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        break

    async def embeddings(self, text: str, keep_alive: str = "5m") -> List[float]:
        """
        Получение эмбеддинга для RAG (bge-m3).
        Aliased from get_embedding.
        """
        payload = {
            "model": "bge-m3", 
            "prompt": text,
            "keep_alive": keep_alive
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/embeddings", json=payload)
            response.raise_for_status()
            return response.json()["embedding"]

    # Backward compatibility for RAG service
    async def get_embedding(self, text: str) -> List[float]:
        return await self.embeddings(text)

    async def generate_base(self, model: str, prompt: str, keep_alive: int = 0):
        """
        Базовый генератор, в основном используется RAM_MANAGER для отправки keep_alive=0 
        чтобы принудительно выгрузить модель из Unified Memory.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "keep_alive": keep_alive
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{self.base_url}/generate", json=payload)
            response.raise_for_status()
            return response.json()

ollama_client = OllamaClient()
