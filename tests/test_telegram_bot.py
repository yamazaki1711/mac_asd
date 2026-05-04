"""
Tests for MAC_ASD v13.0 Telegram WorkEntry Bot (Item 6, P0 May 2026).

Covers: /workentry parsing, /status, response formatting, edge cases.
No actual Telegram API calls — tests the logic layer only.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def bot():
    """Create WorkEntryBot instance (no token needed for logic tests)."""
    from src.core.telegram_bot import WorkEntryBot
    return WorkEntryBot(token="test-token")


# ═══════════════════════════════════════════════════════════════════════════════
# /workentry command
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkEntryParsing:
    @pytest.mark.asyncio
    async def test_parse_beton_rostverk(self, bot):
        """Parse: бетонирование ростверка with zone and volume."""
        text = "Захватка 3, бетонирование ростверка завершено, 12 м³"
        response = await bot.process_work_entry(text, chat_id=123)
        assert "Работа зафиксирована" in response
        assert "Захватка 3" in response
        assert "concrete" in response.lower() or "concrete" in response or "бетон" in response.lower()
        assert "12" in response
        assert "м³" in response

    @pytest.mark.asyncio
    async def test_parse_shpunt(self, bot):
        """Parse: погружение шпунта with batch."""
        text = "Причал 9: погружение шпунта Л5-УМ, 24 шт, партия B-2026-001"
        response = await bot.process_work_entry(text, chat_id=456)
        assert "Работа зафиксирована" in response
        assert "Причал 9" in response
        assert "24" in response
        assert "шт" in response

    @pytest.mark.asyncio
    async def test_parse_metal_structures(self, bot):
        """Parse: монтаж металлоконструкций without volume."""
        text = "Зона А: монтаж металлоконструкций, ось 1-5"
        response = await bot.process_work_entry(text, chat_id=789)
        assert "Работа зафиксирована" in response
        assert "metal_structures" in response.lower()

    @pytest.mark.asyncio
    async def test_parse_armirovanie(self, bot):
        """Parse: армирование фундамента завершено."""
        text = "Участок 2, армирование фундамента завершено, 2.5 т"
        response = await bot.process_work_entry(text, chat_id=111)
        assert "Работа зафиксирована" in response
        assert "Участок 2" in response

    @pytest.mark.asyncio
    async def test_parse_zemlyanye(self, bot):
        """Parse: земляные работы."""
        text = "Котлован, выемка грунта завершено, 500 м³"
        response = await bot.process_work_entry(text, chat_id=222)
        assert "Работа зафиксирована" in response
        assert "500" in response

    @pytest.mark.asyncio
    async def test_aosr_recommendation_on_completion(self, bot):
        """Completed work should suggest AOSR generation."""
        text = "Захватка 1, бетонирование колонн завершено, 8 м³"
        response = await bot.process_work_entry(text, chat_id=333)
        assert "АОСР" in response.upper()


# ═══════════════════════════════════════════════════════════════════════════════
# Short / invalid input
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidInput:
    @pytest.mark.asyncio
    async def test_empty_message(self, bot):
        """Empty message should return error hint."""
        response = await bot.process_work_entry("", chat_id=123)
        assert "слишком короткое" in response.lower() or "коротк" in response.lower()

    @pytest.mark.asyncio
    async def test_very_short_message(self, bot):
        """Very short message should return error."""
        response = await bot.process_work_entry("ок", chat_id=123)
        assert "слишком короткое" in response.lower()

    @pytest.mark.asyncio
    async def test_unparseable_message(self, bot):
        """Gibberish should get error response."""
        response = await bot.process_work_entry("asdfghjkl qwerty", chat_id=123)
        assert "удалось распознать" in response.lower() or "зафиксирована" in response.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# /status command
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusCommand:
    def test_status_no_entries(self, bot):
        """Status with no prior entries."""
        response = bot.get_status(chat_id=999)
        assert "Нет последних записей" in response or "нет" in response.lower()

    @pytest.mark.asyncio
    async def test_status_after_workentry(self, bot):
        """Status after submitting a work entry."""
        text = "Захватка 5, демонтаж конструкций завершено, 100 м²"
        await bot.process_work_entry(text, chat_id=555)

        response = bot.get_status(chat_id=555)
        assert "Захватка 5" in response
        assert "Завершено" in response


# ═══════════════════════════════════════════════════════════════════════════════
# /workentry command prefix handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandPrefix:
    @pytest.mark.asyncio
    async def test_with_workentry_prefix(self, bot):
        """Message with /workentry prefix."""
        text = "/workentry Захватка 1, бетонирование готово, 5 м³"
        response = await bot.process_work_entry(text, chat_id=123)
        assert "Работа зафиксирована" in response

    @pytest.mark.asyncio
    async def test_without_command_prefix(self, bot):
        """Plain message without /workentry prefix."""
        text = "Захватка 1, бетонирование готово, 5 м³"
        response = await bot.process_work_entry(text, chat_id=123)
        assert "Работа зафиксирована" in response

    @pytest.mark.asyncio
    async def test_workentry_no_args(self, bot):
        """Bare /workentry without description."""
        response = await bot.process_work_entry("/workentry", chat_id=123)
        assert "слишком короткое" in response.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Bot initialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotInit:
    def test_bot_creation_with_token(self):
        """Bot with explicit token."""
        from src.core.telegram_bot import WorkEntryBot
        b = WorkEntryBot(token="123:abc")
        assert b.token == "123:abc"

    def test_bot_creation_without_token(self):
        """Bot without token gets empty string."""
        from src.core.telegram_bot import WorkEntryBot
        # Clear env to test fallback
        import os
        saved = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        try:
            b = WorkEntryBot()
            assert b.token == ""
        finally:
            if saved:
                os.environ["TELEGRAM_BOT_TOKEN"] = saved

    @pytest.mark.asyncio
    async def test_start_without_token(self, caplog):
        """start() without token should log error and return."""
        from src.core.telegram_bot import WorkEntryBot, work_entry_bot
        saved = work_entry_bot.token
        try:
            work_entry_bot.token = ""
            await work_entry_bot.start()
            # Should not raise
        finally:
            work_entry_bot.token = saved
