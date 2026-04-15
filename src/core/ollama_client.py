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

    async def chat(self, messages: List[Dict[str, str]], stream: bool = False) -> Any:
        """
        Основной метод для общения с Gemma 4.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": 0.1,  # Для точности в сметах и законах
                "num_ctx": 32768,    # Хороший контекст для длинных PDF
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            if not stream:
                response = await client.post(f"{self.base_url}/chat", json=payload)
                response.raise_for_status()
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

    async def get_embedding(self, text: str) -> List[float]:
        """
        Получение эмбеддинга для RAG (bge-m3).
        """
        payload = {
            "model": "bge-m3", # Используем модель эмбеддингов
            "prompt": text
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/embeddings", json=payload)
            response.raise_for_status()
            return response.json()["embedding"]

ollama_client = OllamaClient()
