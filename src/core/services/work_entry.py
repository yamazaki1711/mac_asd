"""
MAC_ASD v12.0 — WorkEntry Parser (Telegram → OЖР).

Принимает сообщения от прораба через Telegram и создаёт
цифровые записи о выполненных работах (замена бумажному ОЖР).

Форматы сообщений:
    "Захватка 3, бетонирование ростверка завершено, 12 м³"
    "Причал 9: погружение шпунта Л5-УМ, 24 шт, партия B-2026-001"
    "Зона А: монтаж металлоконструкций, ось 1-5"
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class WorkEntryParser:
    """
    Парсер сообщений о выполненных работах.

    Извлекает из свободного текста:
    - Захватку / зону
    - Вид работы
    - Конструктивный элемент
    - Объём
    - Материалы (партии)
    """

    # Паттерны для извлечения
    ZONE_PATTERNS = [
        r"(?:захватка|зона|участок|причал)\s*[\s№#]*(\d+\w*)",
        r"([Пп]ричал\s*[\s№#]*\d+\w*)",
    ]

    VOLUME_PATTERNS = [
        r"(\d+[.,]?\d*)\s*(м³|м3|м\.?\s*п\.?|м\.?пог\.?|шт|т|тонн|кг|м²|м2)",
    ]

    MATERIAL_PATTERNS = [
        r"(?:партия|бетон|арматура|шпунт|свая)\s*([\w\d\-]+)",
    ]

    # Ключевые глаголы завершения
    COMPLETION_VERBS = [
        "завершено", "выполнено", "готово", "сделано", "закончено",
        "залито", "смонтировано", "уложено", "погружено", "забито",
    ]

    # Маппинг ключевых слов → WorkType
    KEYWORD_TO_WORK_TYPE = {
        "бетонирование": "concrete",
        "бетон": "concrete",
        "заливка": "concrete",
        "ростверк": "foundation_monolithic",
        "фундамент": "foundation_monolithic",
        "свая": "foundation_pile",
        "сваи": "foundation_pile",
        "шпунт": "foundation_pile",
        "погружение": "foundation_pile",
        "котлован": "earthwork_excavation",
        "выемка": "earthwork_excavation",
        "земляные": "earthwork_excavation",
        "обратная засыпка": "earthwork_backfill",
        "металлоконструкц": "metal_structures",
        "монтаж": "metal_structures",
        "кладка": "masonry",
        "кирпич": "masonry",
        "стяжка": "finishing_floors",
        "штукатурка": "finishing_walls_ceilings",
        "прокол": "hdd_drilling",
        "ГНБ": "hdd_drilling",
        "демонтаж": "demolition",
        "сварка": "metal_structures",
        "армирование": "concrete",
    }

    def parse(self, raw_text: str) -> Dict[str, Any]:
        """
        Разобрать сообщение о выполненной работе.

        Returns:
            {
                "parsed_ok": bool,
                "zone_name": str or None,
                "work_type": str or None,
                "element_name": str or None,
                "description": str,
                "volume": {"unit": str, "quantity": float} or None,
                "materials": [{"name": str, "batch": str}] or [],
                "is_completion": bool,
                "raw_text": str,
            }
        """
        text = raw_text.strip()
        result = {
            "parsed_ok": False,
            "zone_name": None,
            "work_type": None,
            "element_name": None,
            "description": text,
            "volume": None,
            "materials": [],
            "is_completion": False,
            "raw_text": text,
        }

        if not text or len(text) < 5:
            return result

        text_lower = text.lower()

        # 1. Извлечь захватку/зону
        for pattern in self.ZONE_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                result["zone_name"] = m.group(0).strip()
                break

        # 2. Извлечь вид работы
        for keyword, wt in self.KEYWORD_TO_WORK_TYPE.items():
            if keyword.lower() in text_lower:
                result["work_type"] = wt
                break

        # 3. Извлечь конструктивный элемент (оставшаяся часть после захватки и до глагола)
        element = text
        if result["zone_name"]:
            element = element.replace(result["zone_name"], "", 1).strip(" ,;:-")
        # Remove volume info
        for vp in self.VOLUME_PATTERNS:
            element = re.sub(vp, "", element, flags=re.IGNORECASE)
        # Remove completion verb
        for verb in self.COMPLETION_VERBS:
            element = element.replace(verb, "")
        element = element.strip(" ,;:-")
        if element and not result.get("work_type"):
            result["element_name"] = element[:100]

        # 4. Извлечь объём
        for vp in self.VOLUME_PATTERNS:
            m = re.search(vp, text, re.IGNORECASE)
            if m:
                try:
                    qty = float(m.group(1).replace(",", "."))
                    unit = m.group(2).replace("м3", "м³").replace("м.п.", "м.п.").replace("м.пог.", "м.п.")
                    result["volume"] = {"unit": unit, "quantity": qty}
                except ValueError:
                    logger.debug("Failed to parse volume quantity from text: %s", text[:200])
                break

        # 5. Извлечь материалы (партии)
        for mp in self.MATERIAL_PATTERNS:
            for m in re.finditer(mp, text, re.IGNORECASE):
                result["materials"].append({"name": m.group(0).strip(), "batch": ""})

        # 6. Проверить, является ли сообщение уведомлением о завершении
        result["is_completion"] = any(verb in text_lower for verb in self.COMPLETION_VERBS)

        # Парсинг успешен если нашли хотя бы зону или вид работы
        result["parsed_ok"] = bool(result["zone_name"] or result["work_type"])

        return result


# =============================================================================
# WorkEntry Service — создание записей из Telegram-сообщений
# =============================================================================

class WorkEntryService:
    """
    Сервис приёма данных о выполненных работах.

    Принимает сообщение → парсит → создаёт WorkEntry в БД →
    → возвращает ID записи для дальнейшей обработки (генерация АОСР).
    """

    def __init__(self):
        self.parser = WorkEntryParser()

    async def process_message(
        self,
        raw_text: str,
        project_id: int,
        source: str = "telegram",
        source_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Обработать сообщение о выполненной работе.

        Args:
            raw_text: Текст сообщения
            project_id: ID проекта
            source: Источник (telegram, api, manual)
            source_message_id: ID сообщения в Telegram

        Returns:
            {"status": "ok"|"error", "work_entry_id": int, "parsed": dict, "next_action": str}
        """
        parsed = self.parser.parse(raw_text)

        if not parsed["parsed_ok"]:
            return {
                "status": "error",
                "message": "Не удалось распознать зону или вид работы",
                "parsed": parsed,
                "hint": 'Формат: "Захватка N, вид работы завершено, объём"',
            }

        next_action = "pending"
        if parsed["is_completion"] and parsed["work_type"]:
            next_action = "ready_for_aosr"

        work_entry_id = await self._persist_entry(
            project_id=project_id,
            parsed=parsed,
            raw_text=raw_text,
            source=source,
            source_message_id=source_message_id,
        )

        return {
            "status": "ok",
            "work_entry_id": work_entry_id,
            "parsed": parsed,
            "next_action": next_action,
            "suggestion": self._generate_suggestion(parsed),
        }

    async def _persist_entry(
        self,
        project_id: int,
        parsed: Dict[str, Any],
        raw_text: str,
        source: str = "telegram",
        source_message_id: Optional[str] = None,
    ) -> Optional[int]:
        try:
            from src.db.init_db import Session
            from src.db.models import WorkEntry as WorkEntryModel, ConstructionZone

            with Session() as session:
                zone_name = parsed.get("zone_name") or "Неизвестная зона"
                zone = session.query(ConstructionZone).filter(
                    ConstructionZone.project_id == project_id,
                    ConstructionZone.name == zone_name,
                ).first()

                if zone is None:
                    zone = ConstructionZone(
                        project_id=project_id,
                        name=zone_name,
                        status="in_progress",
                    )
                    session.add(zone)
                    session.flush()

                entry = WorkEntryModel(
                    project_id=project_id,
                    zone_id=zone.id,
                    work_type=parsed.get("work_type") or "unknown",
                    description=parsed.get("description", raw_text[:500]),
                    volume=parsed.get("volume"),
                    source=source,
                    source_message_id=source_message_id,
                    raw_text=raw_text,
                    parsed_ok=True,
                    status="processed" if parsed.get("is_completion") else "pending",
                )
                session.add(entry)
                session.flush()
                entry_id = entry.id
                session.commit()
                logger.info("WorkEntry %d saved: %s → zone %s", entry_id, raw_text[:80], zone_name)
                return entry_id
        except Exception as e:
            logger.warning("WorkEntry DB save skipped (DB unavailable?): %s", e)
            return None

    def _generate_suggestion(self, parsed: Dict[str, Any]) -> str:
        """Сгенерировать подсказку оператору."""
        parts = []
        if parsed["work_type"]:
            from src.core.services.id_requirements import id_requirements
            trail = id_requirements.get_work_type_trail(parsed["work_type"])
            parts.append(f"Вид работ: {parsed['work_type']}")
            parts.append(f"Требуется АОСР: {trail.get('aosr_count', '?')}")
            if trail.get("aook"):
                parts.append("⚠️ Требуется АООК (ответственные конструкции)")
            parts.append(f"Спецжурналы: {', '.join(trail.get('special_journals', []))}")
        return "\n".join(parts)


# Singleton
work_entry_service = WorkEntryService()
