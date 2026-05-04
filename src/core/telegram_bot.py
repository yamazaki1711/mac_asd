"""
MAC_ASD v13.0 — Telegram Bot for WorkEntry (P0 Item 6, May 2026).

Принимает сообщения от полевых инженеров через Telegram:
  /workentry <описание работы>  — зафиксировать выполненную работу
  /status                       — статус последней записи
  /help                         — справка по формату

Формат сообщения:
  "Захватка 3, бетонирование ростверка завершено, 12 м³"
  "Причал 9: погружение шпунта Л5-УМ, 24 шт, партия B-2026-001"

Бот парсит сообщение через WorkEntryParser, создаёт WorkEntry,
и предлагает сгенерировать АОСР.

Configuration:
  TELEGRAM_BOT_TOKEN=...  в .env
  Запуск: python -m src.core.telegram_bot

Dependencies:
  python-telegram-bot>=22.0
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from src.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Bot Handlers
# ═══════════════════════════════════════════════════════════════════════════════

HELP_TEXT = """
📋 *MAC_ASD WorkEntry Bot*

Я принимаю сообщения о выполненных работах от полевых инженеров.

*Формат сообщения:*
  `Захватка N, вид работы завершено, объём`
  `Причал 9: погружение шпунта Л5-УМ, 24 шт`

*Команды:*
  /workentry — зафиксировать работу
  /status — статус последней записи
  /help — эта справка

*Примеры:*
  ✏️ Захватка 3, бетонирование ростверка завершено, 12 м³
  ✏️ Зона А: монтаж металлоконструкций, ось 1-5
  ✏️ Причал 9: погружение шпунта Л5-УМ, 24 шт, партия B-2026-001
  ✏️ Участок 2, армирование фундамента завершено, 2.5 т

После обработки вы получите подтверждение и рекомендацию по АОСР.
"""


class WorkEntryBot:
    """
    Telegram-бот для приёма WorkEntry от полевых инженеров.

    Интегрируется с WorkEntryParser и WorkEntryService для
    автоматической генерации АОСР по факту выполнения работ.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._app = None
        self._last_entries: Dict[int, Dict[str, Any]] = {}  # chat_id → last entry

    # ═════════════════════════════════════════════════════════════════════
    # Message Processing
    # ═════════════════════════════════════════════════════════════════════

    async def process_work_entry(self, text: str, chat_id: int) -> str:
        """
        Обработать сообщение как запись о выполненной работе.

        Returns:
            Форматированный ответ для отправки в Telegram.
        """
        from src.core.services.work_entry import work_entry_service

        # Strip command prefix
        cleaned = text.strip()
        if cleaned.lower().startswith("/workentry"):
            cleaned = cleaned[len("/workentry"):].strip()

        if not cleaned or len(cleaned) < 5:
            return (
                "❌ Сообщение слишком короткое.\n\n"
                "Отправьте описание работы в формате:\n"
                "`Захватка N, вид работы завершено, объём`\n\n"
                "Например: _Захватка 3, бетонирование ростверка завершено, 12 м³_"
            )

        result = await work_entry_service.process_message(
            raw_text=cleaned,
            project_id=1,  # default project
            source="telegram_bot",
        )

        if result["status"] == "error":
            hint = result.get("hint", "")
            return (
                f"⚠️ *Не удалось распознать*\n\n"
                f"_{result.get('message', 'Неизвестная ошибка')}_\n\n"
                f"{hint}\n\n"
                f"Пример: _Захватка 3, бетонирование ростверка завершено, 12 м³_"
            )

        parsed = result["parsed"]
        suggestion = result.get("suggestion", "")

        zones: Dict[str, str] = {"emoji": "📍", "text": parsed.get("zone_name") or "не указана"}
        work_type = parsed.get("work_type") or "не определён"
        volume_info = ""
        if parsed.get("volume"):
            v = parsed["volume"]
            volume_info = f"\n📐 *Объём:* {v['quantity']} {v['unit']}"

        is_completion = "✅ Завершено" if parsed.get("is_completion") else "🔄 В процессе"

        response = (
            f"📋 *Работа зафиксирована*\n\n"
            f"{zones['emoji']} *Зона:* {zones['text']}\n"
            f"🏗 *Вид работ:* {work_type}\n"
            f"📊 *Статус:* {is_completion}"
            f"{volume_info}\n"
        )

        if suggestion:
            response += f"\n───\n{suggestion}"

        # Store last entry
        self._last_entries[chat_id] = {
            "parsed": parsed,
            "timestamp": datetime.now().isoformat(),
        }

        if parsed.get("is_completion"):
            response += (
                "\n\n💡 *Рекомендация:* работа завершена — "
                "запустите генерацию АОСР в веб-интерфейсе: "
                "http://127.0.0.1:8080/documents"
            )

        return response

    def get_status(self, chat_id: int) -> str:
        """Получить статус последней записи для chat_id."""
        last = self._last_entries.get(chat_id)
        if not last:
            return "📭 Нет последних записей. Отправьте /workentry чтобы зафиксировать работу."

        parsed = last["parsed"]
        ts = last["timestamp"][:16].replace("T", " ")

        return (
            f"📋 *Последняя запись* ({ts})\n\n"
            f"📍 Зона: {parsed.get('zone_name') or '—'}\n"
            f"🏗 Вид работ: {parsed.get('work_type') or '—'}\n"
            f"{'✅ Завершено' if parsed.get('is_completion') else '🔄 В процессе'}\n"
        )

    # ═════════════════════════════════════════════════════════════════════
    # Bot Runner
    # ═════════════════════════════════════════════════════════════════════

    async def _handle_message(self, update, context):
        """Обработчик входящих сообщений."""
        text = update.message.text or ""
        chat_id = update.effective_chat.id

        if not text.strip():
            await update.message.reply_text(
                "Отправьте текстовое описание работы. /help для справки."
            )
            return

        text_lower = text.lower().strip()

        if text_lower.startswith("/start"):
            await update.message.reply_text(
                "🏗 *MAC_ASD WorkEntry Bot* готов к работе.\n\n"
                "Отправьте описание выполненной работы текстом.\n"
                "/help — формат и примеры.",
                parse_mode="Markdown",
            )
            return

        if text_lower.startswith("/help"):
            await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
            return

        if text_lower.startswith("/status"):
            status = self.get_status(chat_id)
            await update.message.reply_text(status, parse_mode="Markdown")
            return

        # Treat as work entry
        response = await self.process_work_entry(text, chat_id)
        await update.message.reply_text(response, parse_mode="Markdown")

    async def start(self):
        """Запустить бота (блокирующий вызов)."""
        if not self.token:
            logger.error(
                "TELEGRAM_BOT_TOKEN not set. "
                "Get a token from @BotFather and add to .env: TELEGRAM_BOT_TOKEN=..."
            )
            return

        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
        except ImportError:
            logger.error("python-telegram-bot not installed. pip install python-telegram-bot")
            return

        self._app = Application.builder().token(self.token).build()

        # Handlers
        self._app.add_handler(CommandHandler("start", self._handle_message))
        self._app.add_handler(CommandHandler("help", self._handle_message))
        self._app.add_handler(CommandHandler("status", self._handle_message))
        self._app.add_handler(CommandHandler("workentry", self._handle_message))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        logger.info("WorkEntry Bot starting...")
        await self._app.run_polling()

    def run(self):
        """Синхронный запуск бота."""
        import asyncio
        asyncio.run(self.start())


# Singleton
work_entry_bot = WorkEntryBot()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    work_entry_bot.run()
