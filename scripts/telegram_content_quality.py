"""
MAC_ASD v12.0 — Telegram Content Quality Analyzer.

Для каждого канала извлекает последние N сообщений, классифицирует их
на полезный ASD-контент vs шум (реклама, поздравления, объявления, спам).

Возвращает метрики качества:
  - useful_ratio: доля полезных сообщений
  - total / useful / noise: абсолютные числа
  - categories: расклад по категориям полезного контента
  - top_useful: примеры лучших полезных сообщений

Использование:
  python scripts/telegram_content_quality.py @channel_name
  python scripts/telegram_content_quality.py --batch config/telegram_channels.yaml
  python scripts/telegram_content_quality.py --file data/telegram_search_smeta.yaml
"""

import asyncio
import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
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

MESSAGES_TO_FETCH = 100  # Сколько последних сообщений анализировать
MIN_USEFUL_RATIO = 0.15  # Минимальная доля полезного контента для рекомендации

# =============================================================================
# Классификатор контента (keyword-based, бесплатный)
# =============================================================================

# Полезный ASD-контент: категории и ключевые слова

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
            "реестр", "классификатор", "укрупненный",
            "письмо минстроя", "разъяснение",
        ],
    },
    "document_rules": {
        "label": "Оформление документов",
        "keywords": [
            # Акты и освидетельствование
            "акт освидетельствования", "аоср", "акт скрытых работ",
            "акт приёмки", "акт передачи", "акт осмотра",
            "акт сдачи", "акт приема",
            "освидетельствование", "скрытые работы",
            "приёмка", "сдача-приёмка",
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
            "м-29", "м-15", "ос-3",
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

# Шум: классификация нежелательного контента

NOISE_CATEGORIES = {
    "advertising": {
        "label": "Реклама",
        "keywords": [
            "реклама", "спонсор", "партнёр", "партнер",
            "скидка", "акция", "спецпредложение", "распродажа",
            "цена", "заказать", "купить", "заказ",
            "прайс", "стоимость", "оплата",
            "коммерческое предложение", "кп",
        ],
    },
    "greetings": {
        "label": "Поздравления",
        "keywords": [
            "поздравляем", "с праздником", "с днём", "с днем",
            "с новым годом", "с рождеством", "с 8 марта",
            "с 23 февраля", "с 9 мая", "с днём строителя",
            "с днём победы", "юбилей", "день рождения",
            "желаем", "счастья", "здоровья", "успехов",
        ],
    },
    "promo_events": {
        "label": "Вебинары/Курсы/Акции",
        "keywords": [
            "вебинар", "курс", "обучение", "тренинг",
            "семинар", "конференция", "марафон",
            "регистрация", "запись открыта", "участвуй",
            "бесплатный урок", "мастер-класс",
            "интенсив", "повышение квалификации",
        ],
    },
    "job_ads": {
        "label": "Вакансии",
        "keywords": [
            "вакансия", "требуется", "ищем", "требуются",
            "открыта вакансия", "приглашаем на работу",
            "резюме", "зарплата", "зп ",
        ],
    },
    "announcements": {
        "label": "Объявления",
        "keywords": [
            "анонс", "новый выпуск", "скоро", "не пропустите",
            "подпишись", "подписывайтесь", "ставь лайк",
            "опросик", "голосование",
        ],
    },
}


def classify_message(text: str) -> Dict:
    """
    Классифицирует одно сообщение.

    Returns:
        {
            "is_useful": bool,
            "is_noise": bool,
            "useful_categories": [str],
            "noise_categories": [str],
            "text_preview": str (первые 200 символов),
        }
    """
    if not text:
        return {"is_useful": False, "is_noise": True, "useful_categories": [],
                "noise_categories": ["empty"], "text_preview": ""}

    text_lower = text.lower()
    text_short = text[:200]

    # Проверка шума
    noise_cats = []
    for cat_name, cat_info in NOISE_CATEGORIES.items():
        if any(kw in text_lower for kw in cat_info["keywords"]):
            noise_cats.append(cat_name)

    # Проверка полезного
    useful_cats = []
    for cat_name, cat_info in USEFUL_CATEGORIES.items():
        if any(kw in text_lower for kw in cat_info["keywords"]):
            useful_cats.append(cat_name)

    # Эвристики:
    # - Короткие сообщения-анонсы (<100 символов с ссылкой) → шум
    if len(text) < 100 and ("http" in text_lower or "t.me" in text_lower):
        noise_cats.append("short_link_announcement")

    # - Только эмодзи/стикеры → шум
    if len(text.strip()) < 10:
        noise_cats.append("too_short")

    is_noise = len(noise_cats) > 0
    is_useful = len(useful_cats) > 0 and not is_noise

    # Если и полезное и шум — приоритет шума (рекламная статья про СНиП = шум)
    if is_useful and is_noise:
        is_useful = False

    return {
        "is_useful": is_useful,
        "is_noise": is_noise,
        "useful_categories": useful_cats,
        "noise_categories": noise_cats,
        "text_preview": text_short,
    }


# =============================================================================
# Анализ канала
# =============================================================================

async def analyze_channel(
    client: TelegramClient,
    username: str,
    fetch_count: int = MESSAGES_TO_FETCH,
) -> Optional[Dict]:
    """
    Анализирует контент одного Telegram-канала.

    Returns:
        {
            "username": str,
            "title": str,
            "subscribers": int,
            "total_fetched": int,
            "useful_count": int,
            "noise_count": int,
            "useful_ratio": float,
            "category_breakdown": {category: count},
            "noise_breakdown": {category: count},
            "top_useful": [text_preview, ...],
            "verdict": "recommended" | "borderline" | "skip",
        }
    """
    try:
        entity = await client.get_entity(username)
    except Exception as e:
        print(f"  ❌ @{username}: не найден — {e}")
        return None

    title = getattr(entity, 'title', '') or ''
    print(f"\n{'─'*60}")
    print(f"Анализ: @{username} — {title[:70]}")

    # Fetch messages
    messages = []
    try:
        async for msg in client.iter_messages(entity, limit=fetch_count):
            messages.append(msg)
    except FloodWaitError as e:
        print(f"  ⏳ FLOOD WAIT {e.seconds}s — прерываем")
        return None
    except ChannelPrivateError:
        print(f"  🔒 Приватный канал")
        return None
    except Exception as e:
        print(f"  ⚠️ Ошибка: {e}")
        return None

    if not messages:
        print(f"  ⚠️ Нет сообщений")
        return None

    # Classify
    results = []
    for msg in messages:
        text = getattr(msg, 'message', '') or ''
        classification = classify_message(text)
        results.append(classification)

    useful = [r for r in results if r["is_useful"]]
    noise = [r for r in results if r["is_noise"]]
    neutral = len(results) - len(useful) - len(noise)

    useful_ratio = len(useful) / len(results) if results else 0

    # Category breakdown
    useful_cat_count = {}
    for r in useful:
        for cat in r["useful_categories"]:
            useful_cat_count[cat] = useful_cat_count.get(cat, 0) + 1

    noise_cat_count = {}
    for r in noise:
        for cat in r["noise_categories"]:
            noise_cat_count[cat] = noise_cat_count.get(cat, 0) + 1

    # Verdict
    if useful_ratio >= 0.30:
        verdict = "recommended"
    elif useful_ratio >= MIN_USEFUL_RATIO:
        verdict = "borderline"
    else:
        verdict = "skip"

    # Print summary
    print(f"  Всего: {len(results)} | Полезных: {len(useful)} | Шум: {len(noise)} | Нейтральных: {neutral}")
    print(f"  Полезность: {useful_ratio:.0%} → {verdict}")
    if useful_cat_count:
        cats_str = ", ".join(f"{USEFUL_CATEGORIES.get(c, {}).get('label', c)}: {n}" for c, n in
                           sorted(useful_cat_count.items(), key=lambda x: -x[1])[:3])
        print(f"  Категории: {cats_str}")
    if noise_cat_count:
        noise_str = ", ".join(f"{NOISE_CATEGORIES.get(c, {}).get('label', c)}: {n}" for c, n in
                            sorted(noise_cat_count.items(), key=lambda x: -x[1])[:3])
        print(f"  Шум: {noise_str}")

    # Show sample useful messages
    if useful:
        print(f"  Примеры полезных сообщений:")
        for i, r in enumerate(useful[:3]):
            print(f"    [{i+1}] {r['text_preview'][:120]}")

    return {
        "username": username,
        "title": title,
        "subscribers": getattr(entity, 'participants_count', None),
        "total_fetched": len(results),
        "useful_count": len(useful),
        "noise_count": len(noise),
        "neutral_count": neutral,
        "useful_ratio": round(useful_ratio, 3),
        "category_breakdown": useful_cat_count,
        "noise_breakdown": noise_cat_count,
        "top_useful": [r["text_preview"] for r in useful[:5]],
        "verdict": verdict,
    }


# =============================================================================
# Пакетный режим
# =============================================================================

async def analyze_batch(
    client: TelegramClient,
    channels: List[str],
) -> List[Dict]:
    """Анализирует список каналов."""
    results = []
    for username in channels:
        result = await analyze_channel(client, username)
        if result:
            results.append(result)
        await asyncio.sleep(2)  # Throttle
    return results


def load_channels_from_yaml(path: str) -> List[str]:
    """Извлекает username'ы из YAML-файла (конфиг каналов или результаты поиска)."""
    path = Path(path)
    if not path.exists():
        print(f"[!] Файл не найден: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Убираем комментарии, которые мешают парсингу
    lines = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") and "===" in stripped:
            continue  # Заголовки-комментарии
        lines.append(line)
    clean = "\n".join(lines)

    # Пробуем стандартный парсинг
    try:
        data = yaml.safe_load(clean)
    except yaml.YAMLError:
        data = None

    usernames = []
    if isinstance(data, dict) and "channels" in data:
        for ch in data["channels"]:
            uname = ch.get("username", "").strip().lstrip("@")
            if uname:
                usernames.append(uname)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                uname = item.get("username", "").strip().lstrip("@")
                if uname:
                    usernames.append(uname)

    # Если парсинг не дал результатов — ищем username'ы регуляркой
    if not usernames:
        import re
        for match in re.finditer(r'username:\s*(\S+)', raw):
            usernames.append(match.group(1).lstrip("@"))

    return usernames


def print_summary_table(results: List[Dict]):
    """Выводит сводную таблицу."""
    print(f"\n{'='*80}")
    print(f"СВОДКА ПО КАНАЛАМ (отсортировано по полезности)")
    print(f"{'='*80}")
    print(f"{'Канал':30s} | {'Подп':>6s} | {'Всего':>5s} | {'Полез':>5s} | {'Шум':>4s} | {'%':>5s} | Вердикт")
    print(f"{'-'*30}-+-{'-'*6}-+-{'-'*5}-+-{'-'*5}-+-{'-'*4}-+-{'-'*5}-+-{'-'*12}")

    sorted_results = sorted(results, key=lambda x: x["useful_ratio"], reverse=True)
    for r in sorted_results:
        subs = r.get("subscribers") or 0
        print(f"@{r['username']:29s} | {subs:>6} | {r['total_fetched']:>5} | "
              f"{r['useful_count']:>5} | {r['noise_count']:>4} | {r['useful_ratio']:>4.0%} | "
              f"{r['verdict']}")


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="MAC_ASD Telegram Content Quality Analyzer")
    parser.add_argument("target", nargs="?", help="@channel_name или путь к YAML")
    parser.add_argument("--batch", help="Путь к YAML-конфигу с каналами")
    parser.add_argument("--file", action="append", default=[], help="Путь к YAML-файлу с результатами поиска")
    parser.add_argument("--fetch", type=int, default=MESSAGES_TO_FETCH,
                        help=f"Сколько сообщений анализировать (по умолчанию {MESSAGES_TO_FETCH})")
    args = parser.parse_args()

    if not API_ID or not API_HASH:
        print("=" * 60)
        print("⚠️  Не найден TELEGRAM_API_ID / TELEGRAM_API_HASH")
        print("=" * 60)
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
        channels = []

        if args.target:
            if args.target.startswith("@"):
                channels = [args.target.lstrip("@")]
            elif Path(args.target).exists():
                channels = load_channels_from_yaml(args.target)

        if args.batch:
            channels.extend(load_channels_from_yaml(args.batch))

        if args.file:
            for fpath in args.file:
                channels.extend(load_channels_from_yaml(fpath))

        if not channels:
            print("Укажите @channel_name, --batch config.yaml или --file results.yaml")
            sys.exit(1)

        # Убираем дубликаты
        channels = list(dict.fromkeys(channels))

        print(f"Каналов для анализа: {len(channels)}")
        results = await analyze_batch(client, channels)
        print_summary_table(results)

        # Сохраняем результаты
        out_path = Path(__file__).parent.parent / "data" / "telegram_quality_report.yaml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.dump(results, f, allow_unicode=True, default_flow_style=False)
        print(f"\nОтчёт сохранён: {out_path}")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
