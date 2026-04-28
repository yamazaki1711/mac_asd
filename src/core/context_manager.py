"""
ASD v12.0 — Agent Context Manager.

Управление контекстом агентов (inspired by Deep Agents):
  - Auto-summarization при превышении лимита токенов
  - Файловая разгрузка больших данных на диск
  - Сжатие истории сообщений (keep N recent + summary)
  - Персистентная память между сессиями

Проблема: агенты на Gemma 4 31B имеют 128K контекст.
При анализе 500-страничных PDF контекст переполняется за 2-3 документа.
ContextManager предотвращает потерю контекста.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Conversation Turn
# =============================================================================

@dataclass
class ConversationTurn:
    """Один ход диалога агента."""
    role: str          # "user", "assistant", "system", "tool"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    token_count: int = 0
    compressed: bool = False


# =============================================================================
# Context Manager
# =============================================================================

class ContextManager:
    """
    Управляет контекстом агента, предотвращая переполнение.

    Стратегии:
      1. Keep Recent: хранить N последних сообщений полностью
      2. Summarize Old: сообщения старше N — сжимать в summary
      3. File Offload: большие данные (>threshold) сохранять на диск,
         в контекст вставлять ссылку на файл
      4. Token Budget: жёсткий лимит на общее количество токенов
    """

    # Дефолтные настройки для Gemma 4 31B (128K контекст)
    DEFAULT_MAX_RECENT = 10          # Последние N сообщений хранить полностью
    DEFAULT_SUMMARY_INTERVAL = 5     # Каждые N сообщений делать промежуточный summary
    DEFAULT_OFFLOAD_THRESHOLD = 5000  # Сообщения > N символов → на диск
    DEFAULT_TOKEN_BUDGET = 100_000    # Общий бюджет токенов (из 128K)
    DEFAULT_TOKENS_PER_CHAR = 0.25    # ~1 токен на 4 символа (русский текст)

    def __init__(
        self,
        agent_name: str = "",
        max_recent: int = None,
        offload_threshold: int = None,
        token_budget: int = None,
        storage_dir: str = "",
    ):
        self.agent_name = agent_name or "agent"
        self.max_recent = max_recent or self.DEFAULT_MAX_RECENT
        self.offload_threshold = offload_threshold or self.DEFAULT_OFFLOAD_THRESHOLD
        self.token_budget = token_budget or self.DEFAULT_TOKEN_BUDGET

        # Хранилище
        self.storage_dir = Path(storage_dir or f"/tmp/asd_context/{agent_name}")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Состояние
        self.history: List[ConversationTurn] = []
        self.summaries: List[str] = []
        self.total_tokens: int = 0
        self.files_offloaded: int = 0
        self.truncation_count: int = 0

    # =========================================================================
    # Core: Add Message
    # =========================================================================

    def add_message(self, role: str, content: str) -> Optional[str]:
        """
        Добавить сообщение в историю с авто-управлением контекстом.

        Args:
            role: "user", "assistant", "system", "tool"
            content: текст сообщения

        Returns:
            None если OK, или строка-предупреждение если было усечение
        """
        tokens = self._estimate_tokens(content)
        warning = None

        # Проверка: одиночное сообщение > оффлоад-порога
        if len(content) > self.offload_threshold:
            saved_path = self._offload_to_file(role, content)
            content = (
                f"[Содержимое сохранено в файл: {saved_path.name}]\n"
                f"[Размер: {len(content)} символов, ~{tokens} токенов]\n"
                f"[Первые 500 символов:]\n{content[:500]}..."
            )
            tokens = self._estimate_tokens(content)
            self.files_offloaded += 1
            warning = f"Large message offloaded to {saved_path.name}"

        # Добавляем сообщение
        turn = ConversationTurn(
            role=role,
            content=content,
            token_count=tokens,
        )
        self.history.append(turn)
        self.total_tokens += tokens

        # Проверка бюджета токенов
        if self.total_tokens > self.token_budget:
            self._compress()
            warning = warning or f"Context compressed (budget: {self.token_budget})"

        # Проверка: пора делать промежуточный summary?
        if len(self.history) % self.DEFAULT_SUMMARY_INTERVAL == 0:
            self._maybe_summarize()

        return warning

    # =========================================================================
    # Get Context for LLM
    # =========================================================================

    def get_context(self, max_messages: int = None) -> List[Dict[str, str]]:
        """
        Получить контекст для отправки в LLM.

        Формат: [{"role": "user", "content": "..."}, ...]
        Включает summary старых сообщений + последние N сообщений.

        Args:
            max_messages: максимум сообщений (default: self.max_recent)

        Returns:
            Список сообщений в формате OpenAI
        """
        max_msgs = max_messages or self.max_recent
        messages = []

        # Добавляем summary старых сообщений как system message
        if self.summaries:
            summary_text = "\n".join(f"[Ранее]: {s}" for s in self.summaries[-3:])
            messages.append({
                "role": "system",
                "content": (
                    f"Краткое содержание предыдущего контекста "
                    f"({len(self.summaries)} блоков):\n{summary_text}"
                ),
            })

        # Последние N сообщений
        recent = self.history[-max_msgs:] if len(self.history) > max_msgs else self.history
        for turn in recent:
            role = turn.role
            if role == "tool":
                role = "user"  # OpenAI не принимает role=tool без tool_call_id
            messages.append({
                "role": role,
                "content": turn.content,
            })

        return messages

    def get_context_text(self, max_chars: int = 50000) -> str:
        """
        Получить контекст как строку (для non-OpenAI API).

        Args:
            max_chars: максимальная длина

        Returns:
            Строка контекста
        """
        parts = []
        if self.summaries:
            parts.append("=== РАНЕЕ ===")
            parts.extend(self.summaries[-3:])

        parts.append("=== ТЕКУЩИЙ ДИАЛОГ ===")
        recent = self.history[-self.max_recent:] if len(self.history) > self.max_recent else self.history
        for turn in recent:
            parts.append(f"[{turn.role.upper()}]: {turn.content}")

        full = "\n\n".join(parts)
        if len(full) > max_chars:
            full = full[:max_chars] + "\n...[TRUNCATED]"
        return full

    # =========================================================================
    # Compression
    # =========================================================================

    def _compress(self):
        """
        Сжать контекст: оставить только последние max_recent сообщений,
        остальное заменить на summary.
        """
        if len(self.history) <= self.max_recent:
            return

        to_compress = self.history[:-self.max_recent]
        self.history = self.history[-self.max_recent:]

        # Генерируем summary (упрощённо — без LLM, эвристически)
        summary = self._summarize_turns(to_compress)
        self.summaries.append(summary)

        # Пересчитываем токены
        self.total_tokens = sum(t.token_count for t in self.history)
        self.truncation_count += 1

        logger.info(
            "Context compressed: %d turns → summary, %d remaining, "
            "%d tokens, %d truncations total",
            len(to_compress), len(self.history),
            self.total_tokens, self.truncation_count,
        )

    def _summarize_turns(self, turns: List[ConversationTurn]) -> str:
        """
        Эвристический summary без LLM.

        В production — заменить на LLM-summarization:
          LLM("Summarize this conversation in Russian: " + turns_text)
        """
        user_msgs = []
        assistant_msgs = []
        tool_msgs = 0
        total_chars = 0

        for turn in turns:
            total_chars += len(turn.content)
            if turn.role == "user":
                user_msgs.append(turn.content[:200])
            elif turn.role == "assistant":
                assistant_msgs.append(turn.content[:200])
            elif turn.role == "tool":
                tool_msgs += 1

        summary = (
            f"{len(turns)} сообщений ({total_chars} символов). "
            f"Пользователь: {len(user_msgs)} запросов. "
            f"Агент: {len(assistant_msgs)} ответов. "
            f"Инструменты: {tool_msgs} вызовов. "
        )

        # Ключевые слова из запросов пользователя
        if user_msgs:
            key_topics = ", ".join(
                m[:80] for m in user_msgs[-3:]
            )
            summary += f"Темы: {key_topics}"

        return summary

    def _maybe_summarize(self):
        """Проверить, не пора ли сделать промежуточный summary."""
        # Заглушка — в production вызывает LLM для реферата
        pass

    # =========================================================================
    # File Offload
    # =========================================================================

    def _offload_to_file(self, role: str, content: str) -> Path:
        """Сохранить большое сообщение на диск."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.agent_name}_{role}_{timestamp}_{self.files_offloaded}.txt"
        filepath = self.storage_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Role: {role}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Chars: {len(content)}\n")
            f.write("=" * 60 + "\n")
            f.write(content)

        return filepath

    # =========================================================================
    # Memory Persistence
    # =========================================================================

    def save_state(self, session_id: str = ""):
        """Сохранить состояние контекста на диск."""
        state_file = self.storage_dir / f"state_{session_id or 'default'}.pkl"
        state = {
            "agent_name": self.agent_name,
            "summaries": self.summaries,
            "total_tokens": self.total_tokens,
            "files_offloaded": self.files_offloaded,
            "truncation_count": self.truncation_count,
            "history_last_10": [
                {"role": t.role, "content": t.content[:500]}
                for t in self.history[-10:]
            ],
        }
        with open(state_file, "wb") as f:
            pickle.dump(state, f)
        logger.info("Context state saved: %s", state_file)

    def load_state(self, session_id: str = "") -> bool:
        """Загрузить состояние контекста с диска."""
        state_file = self.storage_dir / f"state_{session_id or 'default'}.pkl"
        if not state_file.exists():
            return False

        try:
            with open(state_file, "rb") as f:
                state = pickle.load(f)
            self.summaries = state.get("summaries", [])
            self.total_tokens = state.get("total_tokens", 0)
            self.files_offloaded = state.get("files_offloaded", 0)
            self.truncation_count = state.get("truncation_count", 0)
            logger.info("Context state loaded: %s", state_file)
            return True
        except Exception as e:
            logger.error("Failed to load context state: %s", e)
            return False

    # =========================================================================
    # Helpers
    # =========================================================================

    def _estimate_tokens(self, text: str) -> int:
        """Грубая оценка количества токенов (русский: ~4 символа/токен)."""
        return max(1, int(len(text) * self.DEFAULT_TOKENS_PER_CHAR))

    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика контекст-менеджера."""
        return {
            "agent": self.agent_name,
            "messages": len(self.history),
            "total_tokens": self.total_tokens,
            "token_budget": self.token_budget,
            "usage_pct": round(self.total_tokens / max(self.token_budget, 1) * 100, 1),
            "summaries": len(self.summaries),
            "files_offloaded": self.files_offloaded,
            "truncations": self.truncation_count,
            "storage": str(self.storage_dir),
        }


# =============================================================================
# ContextManager Registry — один менеджер на агента
# =============================================================================

_contexts: Dict[str, ContextManager] = {}


def get_context_manager(agent_name: str) -> ContextManager:
    """Получить или создать ContextManager для агента."""
    if agent_name not in _contexts:
        _contexts[agent_name] = ContextManager(agent_name=agent_name)
    return _contexts[agent_name]
