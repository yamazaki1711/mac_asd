"""
MAC_ASD v12.0 — Telegram Knowledge Base Ingestion.

Обходит все каналы из telegram_channels.yaml, извлекает последние сообщения,
классифицирует их (полезное/шум), дедуплицирует и сохраняет в базу знаний.

Формат базы знаний: data/telegram_knowledge.yaml
Каждая запись:
  - id: уникальный хеш
  - timestamp: дата сообщения
  - source_channel: @username
  - source_domain: legal/pto/smeta/logistics/procurement
  - category: regulatory_changes | document_rules | technical_knowledge | ...
  - text: полный текст сообщения
  - text_preview: первые 200 символов
  - msg_link: https://t.me/channel/msg_id

Инкрементальность: сохраняет last_msg_id для каждого канала в
data/telegram_ingest_state.yaml — при следующем запуске берёт только новые.

Использование:
  python scripts/telegram_kb_ingest.py              # Все каналы, последние N сообщений
  python scripts/telegram_kb_ingest.py --channel @PTOmanual  # Один канал
  python scripts/telegram_kb_ingest.py --domain pto          # Каналы одного домена
  python scripts/telegram_kb_ingest.py --fetch 200            # Больше сообщений
"""

import asyncio
import hashlib
import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

import yaml
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelPrivateError
from telethon.tl.types import Message

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# =============================================================================
# Конфигурация
# =============================================================================

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_FILE = Path(__file__).parent.parent / "credentials" / "telethon_session"

CHANNELS_CONFIG = Path(__file__).parent.parent / "config" / "telegram_channels.yaml"
KNOWLEDGE_BASE = Path(__file__).parent.parent / "data" / "telegram_knowledge.yaml"
INGEST_STATE = Path(__file__).parent.parent / "data" / "telegram_ingest_state.yaml"

DEFAULT_FETCH_COUNT = 100  # Сколько последних сообщений брать с каждого канала
MIN_TEXT_LENGTH = 50        # Минимальная длина полезного текста

# =============================================================================
# Классификатор (импортирован из telegram_content_quality.py)
# =============================================================================

USEFUL_CATEGORIES = {
    "regulatory_changes": {
        "label": "Изменения в НПА",
        "keywords": [
            "приказ", "постановление", "распоряжение", "изменен",
            "вступил в силу", "вступает в силу", "утвержден", "утвердил",
            "опубликован", "зарегистрирован", "минстрой", "минюст",
            "правительство рф", "госдума", "федеральный закон",
            "пп рф", "постановление правительства",
            "снип", "свод правил", "сп ", "гост р", "гост ",
            "технический регламент", "техрегламент",
            "44-фз", "223-фз", "384-фз", "190-фз", "315-фз",
            "градостроительный кодекс", "грк",
            "извещение об изменении", "проект изменений",
            "актуализирован", "новая редакция",
            "реестр", "классификатор",
            "письмо минстроя", "разъяснение",
        ],
    },
    "document_rules": {
        "label": "Оформление документов",
        "keywords": [
            # Акты и освидетельствование
            "акт освидетельствования", "аоср", "акт скрытых работ",
            "акт приёмки", "акт передачи", "акт осмотра",
            "акт сдачи", "акт приема", "акт ",
            "освидетельствование", "скрытые работы",
            "приёмка", "сдача-приёмка", "приемка",
            # Исполнительная документация
            "исполнительная документация", "исполнительная схема",
            "исполнительная геодезическая", "исполнительная съёмка",
            "состав исполнительной", "перечень исполнительной",
            "реестр исполнительной", "комплект исполнительной",
            # Журналы
            "общий журнал работ", "специальный журнал",
            "журнал бетонных работ", "журнал сварочных работ",
            "журнал входного контроля", "журнал авторского надзора",
            "журнал производства", "журнал работ",
            "запись в журнале", "заполнение журнала",
            # Формы КС и другие
            "кс-2", "кс-3", "кс-6а", "кс-11", "кс-14",
            "кс-", "м-29", "м-15", "ос-3",
            # Оформление
            "оформление", "заполнение", "бланк",
            "подпись", "реквизит", "печать", "штамп",
            "прошивка", "пронумеровано", "прошнуровано",
            "титульный лист", "содержание тома",
            "нумерация", "шифр документа", "альбом",
            "комплект документации", "комплект чертежей",
            "форма акта", "форма журнала", "новая форма",
            "изменение формы", "изменение порядка",
            # Нормативные требования к оформлению
            "приказ ростехнадзора", "рд-11-02", "рд-11-05",
            "порядок ведения", "порядок оформления",
            "требования к оформлению", "правила оформления",
            "ведомость", "ведомость объёмов", "ведомость работ",
            # Разрешительная
            "разрешительная документация", "разрешение на строительство",
            # Стройконтроль и приёмка
            "стройконтроль", "строительный контроль",
        ],
    },
    "technical_knowledge": {
        "label": "Технические знания",
        "keywords": [
            "технология", "технологическая карта", "ттк",
            "пос", "ппр", "проект производства работ",
            "проект организации строительства",
            "стройгенплан", "календарный план",
            "монтаж", "демонтаж", "устройство", "возведение",
            "бетонирование", "армирование", "опалубка",
            "сварка", "сварной", "сварочный",
            "грунт", "основание", "фундамент", "свая",
            "кровля", "фасад", "кладка", "стяжка",
            "геодезия", "разбивка", "нивелир",
            "контроль качества", "приёмка", "испытание",
            "неразрушающий контроль", "узк", "вик", "мк",
            "прочность", "морозостойкость", "водонепроницаемость",
            "сертификат", "паспорт качества", "декларация",
            "материал", "конструкция", "изделие",
            "строительная лаборатория", "лабораторный контроль",
        ],
    },
    "industry_analysis": {
        "label": "Отраслевая аналитика",
        "keywords": [
            "анализ", "обзор", "тенденция", "статистика",
            "ценообразование", "сметная стоимость", "индексация",
            "нмцк", "начальная максимальная цена",
            "конкуренция", "рынок", "подряд",
            "рентабельность", "маржинальность",
            "себестоимость", "накладные расходы",
            "импортозамещение", "локализация",
            "цифровизация", "тим", "bim",
            "производительность труда",
        ],
    },
    "case_law": {
        "label": "Судебная/правовая практика",
        "keywords": [
            "судебная практика", "арбитраж", "суд",
            "решение суда", "постановление суда", "определение",
            "кассация", "апелляция", "верховный суд",
            "спор", "иск", "претензия",
            "неустойка", "штраф", "пени",
            "банкротство", "субсидиарная ответственность",
            "реестр недобросовестных", "рнп",
            "односторонний отказ", "расторжение контракта",
        ],
    },
}

NOISE_CATEGORIES = {
    "advertising": {
        "label": "Реклама",
        "keywords": [
            "реклама", "спонсор", "партнёр", "партнер",
            "скидка", "акция", "спецпредложение", "распродажа",
            "цена", "заказать", "купить",
            "прайс", "стоимость", "оплата",
            "коммерческое предложение",
        ],
    },
    "greetings": {
        "label": "Поздравления",
        "keywords": [
            "поздравляем", "с праздником", "с днём", "с днем",
            "с новым годом", "с рождеством",
            "с днём строителя", "юбилей", "день рождения",
            "желаем", "счастья", "здоровья",
        ],
    },
    "promo_events": {
        "label": "Вебинары/Курсы",
        "keywords": [
            "вебинар", "курс", "обучение", "тренинг",
            "семинар", "конференция", "марафон",
            "регистрация", "запись открыта",
            "бесплатный урок", "мастер-класс",
            "интенсив", "повышение квалификации",
        ],
    },
    "job_ads": {
        "label": "Вакансии",
        "keywords": [
            "вакансия", "требуется", "ищем", "требуются",
            "открыта вакансия", "приглашаем на работу",
            "резюме", "зарплата",
        ],
    },
    "announcements": {
        "label": "Объявления",
        "keywords": [
            "анонс", "новый выпуск", "скоро", "не пропустите",
            "подпишись", "подписывайтесь",
            "опрос", "голосование",
        ],
    },
}


# =============================================================================
# ASD Relevance Filter — железный заслон от нестройконтента
# =============================================================================

# Контент, который НИКОГДА не нужен ASD (даже если содержит строй-термины)
ASD_IRRELEVANT_PATTERNS: List[str] = [
    # Политика / чиновники
    "мишустин", "путин", "собянин", "хуссейн", "губернатор",
    "правительство рф", "совет федерации", "госдума",
    "выборы", "голосование", "партия",
    # Макроэкономика / рынки (не строительные)
    "рынок недвижимости", "цены на квартиры", "ипотека", "ипотечный",
    "ключевая ставка", "ставка цб", "курс валют", "инфляция",
    "падение рынка", "рост рынка", "аналитика рынка",
    # Военная тематика / БПЛА
    "бпла", "беспилотник", "дрон", "сво", "мобилизация",
    "вооружение", "минобороны", "военный",
    # Общие новости без ASD-ценности
    "банкротство застройщика", "обманутые дольщики",
    "элитный жк", "премиум жк", "рейтинг застройщиков",
    "открытие жк", "заселение жк",
    # Non-construction business
    "стартап", "венчурный", "инвестиции в it", "искусственный интеллект",
    "нейросеть", "машинное обучение",
    # Развлекалово
    "мем", "прикол", "юмор", "анекдот",
]

# Сильные сигналы ASD-релевантности — перевешивают IRRELEVANT
ASD_STRONG_SIGNALS: List[str] = [
    # Нормативка
    "свод правил", "сп 4", "сп 5", "сп 6", "сп 7", "сп 1",
    "гост р", "гост 2", "гост 3", "гост 5", "гост р 5", "гост р 7",
    "снип", "технический регламент", "приказ минстроя", "приказ ростехнадзора",
    "344/пр", "468/пр", "1026/пр",
    "постановление правительства", "пп рф", "распоряжение правительства",
    "изменения в методику", "изменения в положение",
    "утверждён", "утверждена", "вступает в силу",
    # Исполнительная документация
    "аоср", "аоок", "акт освидетельствования", "скрытые работы",
    "исполнительная документация", "исполнительная схема", "игс",
    "журнал работ", "ожр", "жбр", "жср", "жвк", "спецжурнал",
    "кс-2", "кс-3", "кс-6а", "акт выполненных работ",
    "справка о стоимости", "процент выполнения",
    # Проектная документация / экспертиза
    "проектная документация", "проектной документации",
    "государственная экспертиза", "госэкспертиза",
    "главгосэкспертиза", "заключение экспертизы",
    # Стройконтроль / испытания
    "стройконтроль", "технадзор", "лабораторный контроль",
    "неразрушающий контроль", "узк", "ультразвуковой",
    "протокол испытаний", "входной контроль",
    "сертификат качества", "паспорт изделия",
    # Технология строительства (stem-формы)
    "армирование", "бетонирование", "опалубка", "сваи",
    "шпунт", "котлован", "земляные работы",
    "сварка", "сварной шов", "сварного шва", "сварные",
    "монтаж", "монтажа", "демонтаж",
    "кондуктор", "колонн", "сборных ж",
    "бетон", "арматура", "щебень", "металлопрокат",
    "фундамент", "кровля", "фасад",
    # Контракты / тендеры / УФАС
    "44-фз", "223-фз", "нмцк", "банковская гарантия",
    "договор подряда", "субподряд", "генподряд",
    "протокол разногласий", "досудебная претензия",
    "уфас", "рнп", "реестр недобросовестных",
    "госконтракт", "госзакуп",
    "односторонний отказ", "расторжение контракта",
    # Сметы
    "фер", "тер", "гэсн", "сметный расчёт", "единичная расценка",
    "ведомость объёмов", "сметная стоимость", "сметной стоимости",
    "индексы минстроя", "мониторинг цен",
    # BIM / ТИМ / цифровизация стройки
    "bim", "тим", "цифровая модель", "среда общих данных",
    "информационное моделирование",
    "кпср", "xml", "гис егрз",
    # Судебная практика (строительная)
    "арбитражный суд", "кассация", "апелляция",
    "неустойка", "проценты по 395", "убытки",
    "определение вс", "постановление суда",
]


def _has_asd_relevance(text: str) -> bool:
    """Проверяет, относится ли текст к домену ASD.

    Логика: если есть сильный ASD-сигнал → пропускаем.
    Если есть IRRELEVANT-паттерн И нет сильного сигнала → отсекаем.
    """
    text_lower = text.lower()

    # Сильные сигналы — мгновенный пропуск
    for sig in ASD_STRONG_SIGNALS:
        if sig in text_lower:
            return True

    # Без сильного сигнала — проверяем IRRELEVANT
    for pat in ASD_IRRELEVANT_PATTERNS:
        if pat in text_lower:
            return False

    # Нет ни сильного сигнала, ни антипаттерна → сомнительно, отсекаем
    # (контент без нормативки/технологии/ИД ASD не нужен)
    return False


def classify_message(text: str) -> Tuple[bool, List[str]]:
    """
    Возвращает (is_useful, [category_names]).
    Приоритет: шум → ASD-релевантность → полезные категории.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return False, []

    text_lower = text.lower()

    # Tier 1: Проверка шума (реклама/спам — жёсткий отсев)
    for cat_info in NOISE_CATEGORIES.values():
        if any(kw in text_lower for kw in cat_info["keywords"]):
            return False, []

    # Tier 2: ASD-релевантность (ключевой фильтр)
    if not _has_asd_relevance(text):
        return False, []

    # Tier 3: Категоризация полезного
    useful_cats = []
    for cat_name, cat_info in USEFUL_CATEGORIES.items():
        if any(kw in text_lower for kw in cat_info["keywords"]):
            useful_cats.append(cat_name)

    return len(useful_cats) > 0, useful_cats


# =============================================================================
# Загрузка / сохранение
# =============================================================================

def load_channels(domain: Optional[str] = None) -> List[Dict]:
    """Загрузить каналы из YAML-конфига. Фильтр по домену."""
    if not CHANNELS_CONFIG.exists():
        return []
    with open(CHANNELS_CONFIG, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    channels = data.get("channels", [])
    if domain:
        channels = [ch for ch in channels if ch.get("domain") == domain]
    return channels


def load_knowledge_base() -> List[Dict]:
    """Загрузить существующую базу знаний."""
    if not KNOWLEDGE_BASE.exists():
        return []
    with open(KNOWLEDGE_BASE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def save_knowledge_base(entries: List[Dict]):
    """Сохранить базу знаний."""
    KNOWLEDGE_BASE.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWLEDGE_BASE, "w", encoding="utf-8") as f:
        yaml.dump(entries, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_ingest_state() -> Dict[str, int]:
    """Загрузить состояние ингеста (last_msg_id по каналам)."""
    if not INGEST_STATE.exists():
        return {}
    with open(INGEST_STATE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def save_ingest_state(state: Dict[str, int]):
    """Сохранить состояние ингеста."""
    INGEST_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(INGEST_STATE, "w", encoding="utf-8") as f:
        yaml.dump(state, f, allow_unicode=True)


def compute_msg_id_hash(text: str) -> str:
    """SHA256 хеш текста для дедупликации."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# =============================================================================
# Ингест одного канала
# =============================================================================

async def ingest_channel(
    client: TelegramClient,
    channel_config: Dict,
    fetch_count: int,
    seen_hashes: Set[str],
    last_msg_id: Optional[int] = None,
) -> Tuple[List[Dict], Optional[int], Dict]:
    """
    Извлекает и классифицирует сообщения одного канала.

    Returns:
        (new_entries, new_last_msg_id, stats)
    """
    username = channel_config.get("username", "").strip()
    domain = channel_config.get("domain", "unknown")
    priority = channel_config.get("priority", "medium")

    stats = {
        "username": username,
        "fetched": 0,
        "useful": 0,
        "noise": 0,
        "new": 0,
        "skipped_duplicate": 0,
        "skipped_short": 0,
        "error": None,
    }

    # Получаем entity канала
    try:
        entity = await client.get_entity(username)
    except ChannelPrivateError:
        stats["error"] = "private"
        return [], None, stats
    except Exception as e:
        stats["error"] = str(e)[:80]
        return [], None, stats

    channel_title = getattr(entity, "title", "") or username
    print(f"  📥 @{username} — {channel_title[:60]}")

    # Извлекаем сообщения
    messages = []
    new_last_msg_id = last_msg_id
    try:
        iter_args = {"entity": entity, "limit": fetch_count}
        if last_msg_id:
            iter_args["min_id"] = last_msg_id

        async for msg in client.iter_messages(**iter_args):
            messages.append(msg)
    except FloodWaitError as e:
        print(f"     ⏳ FLOOD WAIT {e.seconds}s")
        await asyncio.sleep(min(e.seconds, 10))
        stats["error"] = f"flood_wait_{e.seconds}s"
        return [], None, stats
    except Exception as e:
        stats["error"] = str(e)[:80]
        return [], None, stats

    stats["fetched"] = len(messages)

    if not messages:
        print(f"     ⚠️ Нет новых сообщений")
        return [], last_msg_id, stats

    # Обновляем last_msg_id (ID первого сообщения = самое новое)
    if messages:
        new_last_msg_id = messages[0].id

    # Классифицируем
    new_entries = []
    for msg in messages:
        text = (getattr(msg, "message", "") or "").strip()
        if not text:
            stats["skipped_short"] += 1
            continue
        if len(text) < MIN_TEXT_LENGTH:
            stats["skipped_short"] += 1
            continue

        is_useful, categories = classify_message(text)

        if not is_useful:
            stats["noise"] += 1
            continue

        stats["useful"] += 1

        # Дедупликация
        msg_hash = compute_msg_id_hash(text)
        if msg_hash in seen_hashes:
            stats["skipped_duplicate"] += 1
            continue

        seen_hashes.add(msg_hash)
        stats["new"] += 1

        # Формируем запись
        msg_date = getattr(msg, "date", None)
        entry = {
            "id": msg_hash,
            "timestamp": msg_date.isoformat() if msg_date else "unknown",
            "source_channel": f"@{username}",
            "source_domain": domain,
            "source_priority": priority,
            "categories": categories,
            "category_labels": [USEFUL_CATEGORIES[c]["label"] for c in categories],
            "text": text,
            "text_preview": text[:200],
            "msg_link": f"https://t.me/{username}/{msg.id}",
        }
        new_entries.append(entry)

    # Статистика
    dup_skipped = stats["skipped_duplicate"]
    short_skipped = stats["skipped_short"]
    print(f"     fetched={stats['fetched']} useful={stats['useful']} new={stats['new']} "
          f"noise={stats['noise']} dup={dup_skipped} short={short_skipped}")

    return new_entries, new_last_msg_id, stats


# =============================================================================
# Главный цикл
# =============================================================================

async def run_ingest(
    client: TelegramClient,
    channels: List[Dict],
    fetch_count: int,
    incremental: bool = True,
):
    """Обходит все каналы и пополняет базу знаний."""
    print(f"\n{'='*60}")
    print(f"ИНГЕСТ ЗНАНИЙ ИЗ TELEGRAM")
    print(f"Каналов: {len(channels)} | Сообщений с канала: {fetch_count}")
    print(f"{'='*60}\n")

    # Загружаем существующее
    kb = load_knowledge_base()
    state = load_ingest_state() if incremental else {}
    seen_hashes = {e["id"] for e in kb}

    all_stats = []
    total_new = 0
    total_useful = 0
    total_fetched = 0

    for ch in channels:
        username = ch.get("username", "")
        if not username:
            continue

        last_id = state.get(username) if incremental else None
        new_entries, new_last_id, stats = await ingest_channel(
            client, ch, fetch_count, seen_hashes, last_id
        )
        all_stats.append(stats)

        if new_entries:
            kb.extend(new_entries)
            total_new += len(new_entries)

        if new_last_id and incremental:
            state[username] = new_last_id

        if stats.get("useful", 0):
            total_useful += stats["useful"]
        if stats.get("fetched", 0):
            total_fetched += stats["fetched"]

        await asyncio.sleep(2)  # Throttle между каналами

    # Сохраняем
    if total_new > 0:
        save_knowledge_base(kb)
        print(f"\n  💾 База знаний сохранена: {KNOWLEDGE_BASE}")
        print(f"     Всего записей: {len(kb)} (+{total_new})")

    if incremental:
        save_ingest_state(state)

    # Сводка
    print(f"\n{'='*60}")
    print(f"СВОДКА ИНГЕСТА")
    print(f"{'='*60}")
    print(f"  Каналов обработано: {len(all_stats)}")
    print(f"  Всего сообщений извлечено: {total_fetched}")
    print(f"  Полезных (до дедупликации): {total_useful}")
    print(f"  Новых уникальных записей: {total_new}")
    print(f"  Всего в базе знаний: {len(kb)}")

    # По доменам
    domain_stats = {}
    for stat in all_stats:
        if stat.get("error"):
            continue
        # Находим домен для этого канала
        uname = stat["username"]
        for ch in channels:
            if ch.get("username") == uname:
                dom = ch.get("domain", "?")
                ds = domain_stats.get(dom, {"channels": 0, "new": 0, "useful": 0})
                ds["channels"] += 1
                ds["new"] += stat["new"]
                ds["useful"] += stat["useful"]
                domain_stats[dom] = ds
                break

    print(f"\n  По доменам:")
    for dom, ds in sorted(domain_stats.items()):
        print(f"    {dom:15s}: {ds['channels']:>2} каналов, {ds['new']:>4} новых, {ds['useful']:>4} полезных")

    # Ошибки
    errors = [s for s in all_stats if s.get("error")]
    if errors:
        print(f"\n  ⚠️ Ошибки ({len(errors)}):")
        for e in errors:
            print(f"    @{e['username']}: {e['error']}")

    return kb


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="MAC_ASD Telegram Knowledge Base Ingestion")
    parser.add_argument("--channel", help="Обработать один канал (@username)")
    parser.add_argument("--domain", help="Обработать каналы одного домена (legal/pto/smeta/logistics/procurement)")
    parser.add_argument("--fetch", type=int, default=DEFAULT_FETCH_COUNT,
                        help=f"Сообщений с канала (по умолчанию {DEFAULT_FETCH_COUNT})")
    parser.add_argument("--full", action="store_true",
                        help="Полный перезабор (игнорировать инкрементальное состояние)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только статистика, без сохранения")
    args = parser.parse_args()

    if not API_ID or not API_HASH:
        print("⚠️  TELEGRAM_API_ID / TELEGRAM_API_HASH не найдены в .env")
        sys.exit(1)

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("⚠️  Не авторизован. Запусти telegram_scout.py сначала.")
        sys.exit(1)

    try:
        me = await client.get_me()
        print(f"Авторизован: {me.first_name} (@{me.username})")

        # Определяем список каналов
        if args.channel:
            username = args.channel.lstrip("@")
            # Ищем в конфиге или создаём минимальную запись
            all_channels = load_channels()
            channel = next((ch for ch in all_channels if ch.get("username") == username), None)
            if not channel:
                channel = {"username": username, "domain": "unknown", "priority": "medium"}
            channels = [channel]
        else:
            channels = load_channels(domain=args.domain)

        if not channels:
            print("Нет каналов для обработки.")
            sys.exit(0)

        incremental = not args.full
        await run_ingest(client, channels, args.fetch, incremental=incremental)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
