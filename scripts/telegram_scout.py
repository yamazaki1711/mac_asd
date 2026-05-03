"""
MAC_ASD v12.0 — Telegram Channel Scout (Telethon MTProto).

Валидация существующих каналов из telegram_channels.yaml +
поиск новых каналов для пустых доменов (smeta, logistics, procurement).

Требуется: api_id и api_hash от https://my.telegram.org/apps
Сохранить в .env: TELEGRAM_API_ID=... TELEGRAM_API_HASH=...

Режимы:
  --validate   Проверить все каналы из config/telegram_channels.yaml
  --search     Поиск каналов по домену (smeta, logistics, procurement)
  --all        Валидация + поиск
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

import yaml
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    UsernameNotOccupiedError,
    FloodWaitError,
)
from telethon.tl.types import Channel, User

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.environ.get("TELEGRAM_PHONE", "")
TELEGRAM_CODE = os.environ.get("TELEGRAM_CODE", "")

CHANNELS_CONFIG = Path(__file__).parent.parent / "config" / "telegram_channels.yaml"
SESSION_FILE = Path(__file__).parent.parent / "credentials" / "telethon_session"


# =============================================================================
# Поисковые запросы для пустых доменов
# =============================================================================

DOMAIN_SEARCH_QUERIES = {
    "smeta": [
        "сметчик строительный",
        "сметное дело",
        "смета строительство",
        "ФЕР ТЕР расценки",
        "сметный консалтинг",
        "construction estimate Russia",
    ],
    "logistics": [
        "логистика строительство",
        "поставки стройматериалов",
        "снабжение стройка",
        "перевозка строительных грузов",
        "construction logistics",
    ],
    "procurement": [
        "тендеры строительство",
        "госзакупки строительные",
        "закупки стройка",
        "44-ФЗ закупки",
        "тендерный специалист",
        "construction procurement Russia",
    ],
}


# =============================================================================
# Валидация существующих каналов
# =============================================================================

def load_channels() -> List[Dict]:
    """Загрузить каналы из YAML-конфига."""
    if not CHANNELS_CONFIG.exists():
        print(f"[!] Конфиг не найден: {CHANNELS_CONFIG}")
        return []
    with open(CHANNELS_CONFIG, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("channels", [])


async def validate_channels(client: TelegramClient) -> Dict[str, List]:
    """
    Проверить все каналы из конфига через Telethon.

    Returns:
        {"valid": [...], "not_found": [...], "private": [...], "errors": [...]}
    """
    channels = load_channels()
    print(f"\n{'='*60}")
    print(f"Валидация {len(channels)} каналов из telegram_channels.yaml")
    print(f"{'='*60}\n")

    results = {"valid": [], "not_found": [], "private": [], "errors": []}

    for ch in channels:
        username = ch.get("username", "").strip().lstrip("@")
        domain = ch.get("domain", "?")
        display = ch.get("display_name", username)

        if not username:
            continue

        try:
            entity = await client.get_entity(username)
            sub_count = getattr(entity, "participants_count", None)
            if sub_count is None:
                sub_count = "?"

            is_channel = isinstance(entity, Channel)
            is_broadcast = getattr(entity, "broadcast", False)

            results["valid"].append({
                "username": username,
                "title": entity.title,
                "subscribers": sub_count,
                "is_channel": is_channel,
                "is_broadcast": is_broadcast,
                "domain": domain,
                "display": display,
            })
            print(f"  ✅ @{username:30s} → {entity.title[:50]:50s} подп: {sub_count}")

        except UsernameNotOccupiedError:
            results["not_found"].append(username)
            print(f"  ❌ @{username:30s} → НЕ НАЙДЕН (удалён или переименован)")

        except ChannelPrivateError:
            results["private"].append(username)
            print(f"  🔒 @{username:30s} → ПРИВАТНЫЙ (закрыт)")

        except FloodWaitError as e:
            wait = e.seconds
            print(f"  ⏳ FLOOD WAIT {wait} сек — пропускаем...")
            results["errors"].append({"username": username, "error": f"flood_wait_{wait}s"})
            await asyncio.sleep(min(wait, 10))

        except Exception as e:
            results["errors"].append({"username": username, "error": str(e)})
            print(f"  ⚠️ @{username:30s} → ошибка: {e}")

        # Throttle: 1 запрос в 2 секунды (Telegram лимит ~30/мин)
        await asyncio.sleep(2)

    # Сводка
    print(f"\n{'='*60}")
    print(f"Итого: {len(results['valid'])} OK, {len(results['not_found'])} не найдено, "
          f"{len(results['private'])} приватных, {len(results['errors'])} ошибок")
    print(f"{'='*60}")

    # Доменная сводка
    domains = {}
    for v in results["valid"]:
        d = v["domain"]
        domains[d] = domains.get(d, 0) + 1
    print("\nПо доменам:")
    for d, c in sorted(domains.items()):
        print(f"  {d:15s}: {c} каналов")
    empty = [d for d in ("smeta", "logistics", "procurement") if d not in domains]
    if empty:
        print(f"\n⚠️  Пустые домены: {', '.join(empty)} — нужен поиск (--search)")

    return results


# =============================================================================
# Поиск новых каналов
# =============================================================================

async def search_channels(
    client: TelegramClient,
    domain: Optional[str] = None,
) -> Dict[str, List]:
    """
    Поиск каналов через глобальный поиск Telegram.

    Args:
        domain: smeta, logistics, procurement (или None = все пустые домены)

    Returns:
        {domain: [{"username": ..., "title": ..., "subscribers": ...}]}
    """
    domains_to_search = [domain] if domain else ["smeta", "logistics", "procurement"]
    results = {}

    for dom in domains_to_search:
        queries = DOMAIN_SEARCH_QUERIES.get(dom, [])
        if not queries:
            continue

        print(f"\n{'='*60}")
        print(f"Поиск каналов для домена: {dom}")
        print(f"Запросы: {', '.join(queries)}")
        print(f"{'='*60}\n")

        found = []
        seen = set()

        for query in queries:
            try:
                # Глобальный поиск публичных чатов
                async for dialog in client.iter_dialogs():
                    if dialog.is_channel and dialog.entity.username:
                        username = dialog.entity.username.lower()
                        title = dialog.entity.title.lower()
                        if username in seen:
                            continue

                        # Проверяем релевантность по названию/описанию
                        query_words = set(query.lower().split())
                        title_words = set(title.split())
                        if query_words & title_words:
                            seen.add(username)
                            found.append({
                                "username": dialog.entity.username,
                                "title": dialog.entity.title,
                                "subscribers": getattr(dialog.entity, "participants_count", "?"),
                                "query": query,
                            })
                            print(f"  📌 @{dialog.entity.username:30s} → {dialog.entity.title[:50]}")

                await asyncio.sleep(2)

            except FloodWaitError as e:
                print(f"  ⏳ FLOOD WAIT {e.seconds}с")
                await asyncio.sleep(min(e.seconds, 10))
            except Exception as e:
                print(f"  ⚠️ Ошибка поиска '{query}': {e}")

        results[dom] = found
        print(f"\n  Найдено для {dom}: {len(found)} каналов")

    return results


# =============================================================================
# Генерация YAML-фрагментов для найденных каналов
# =============================================================================

def generate_yaml_snippet(domain: str, channels: List[Dict]) -> str:
    """Сгенерировать YAML-фрагмент для добавления в telegram_channels.yaml."""
    if not channels:
        return f"# {domain}: каналов не найдено\n"

    lines = [f"  # === {domain.upper()} — найдено {len(channels)} каналов ==="]
    for ch in channels[:20]:
        username = ch["username"]
        title = ch["title"][:80]
        subs = ch.get("subscribers", "?")
        lines.append(f"  - username: {username}")
        lines.append(f"    domain: {domain}")
        lines.append(f"    display_name: \"{title}\"")
        lines.append(f"    url: \"https://t.me/{username}\"")
        lines.append(f"    description: >")
        lines.append(f"      {title}. Подписчиков: {subs}. Найден через Telethon search.")
        lines.append(f"    category: {domain}_practice")
        lines.append(f"    priority: medium")
        lines.append(f"    focus_areas: []")
        lines.append(f"    subscriber_count: \"{subs}\"")
        lines.append(f"    engagement_rate: \"неизвестно\"")
        lines.append(f"    expected_trap_density: unknown")
        lines.append("")
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="MAC_ASD Telegram Channel Scout")
    parser.add_argument("--validate", action="store_true", help="Валидация каналов из YAML")
    parser.add_argument("--search", type=str, nargs="?", const="all",
                        help="Поиск каналов для домена (smeta/logistics/procurement/all)")
    parser.add_argument("--all", action="store_true", help="Валидация + поиск по всем пустым доменам")
    args = parser.parse_args()

    if not API_ID or not API_HASH:
        print("=" * 60)
        print("⚠️  Не найден TELEGRAM_API_ID / TELEGRAM_API_HASH")
        print("")
        print("1. Иди на https://my.telegram.org/apps")
        print("2. Создай приложение (любое имя, например 'MAC_ASD_Scout')")
        print("3. Скопируй api_id и api_hash")
        print("4. Добавь в .env:")
        print("   TELEGRAM_API_ID=12345678")
        print("   TELEGRAM_API_HASH=abc123def456...")
        print("=" * 60)
        sys.exit(1)

    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        if not TELEGRAM_PHONE:
            print("Нужен TELEGRAM_PHONE в .env для первого входа")
            sys.exit(1)
        await client.send_code_request(TELEGRAM_PHONE)
        code = TELEGRAM_CODE or input("Код из Telegram: ")
        if not code:
            print("Нужен TELEGRAM_CODE в .env или ввод кода")
            sys.exit(1)
        await client.sign_in(TELEGRAM_PHONE, code)
    try:
        me = await client.get_me()
        print(f"Авторизован как: {me.first_name} (@{me.username})")

        if args.validate or args.all:
            await validate_channels(client)

        if args.search or args.all:
            domain = None if args.search in (None, "all") else args.search
            results = await search_channels(client, domain)
            for dom, channels in results.items():
                snippet = generate_yaml_snippet(dom, channels)
                snippet_path = Path(__file__).parent.parent / "data" / f"telegram_search_{dom}.yaml"
                snippet_path.parent.mkdir(parents=True, exist_ok=True)
                snippet_path.write_text(snippet, encoding="utf-8")
                print(f"\n  → YAML-фрагмент сохранён: {snippet_path}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
