import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')
from telethon import TelegramClient
from telethon.errors import UsernameNotOccupiedError, ChannelPrivateError, FloodWaitError

USERNAMES = [
    "smety", "smetnoedelo", "smetchik", "smeta_i_stoimost",
    "smeta_construction", "smetnoe_delo", "smetnyi_otdel",
    "SmetaPro", "smeta_ru", "smety_ru",
    "logistika_stroitelstvo", "snabzhenie_stroyka", "logistics_construction",
    "stroyka_snab", "postavki_stroyka", "stroyka_logist",
    "tendery_stroitelnye", "tender_stroyka", "goszakupki_stroitelnye",
    "zakupki_stroyka", "tendernyi_otdel",
    "pto_doc", "ispolnitelnaya", "asbuilt",
]

async def main():
    client = TelegramClient('credentials/telethon_session',
                           int(os.environ['TELEGRAM_API_ID']),
                           os.environ['TELEGRAM_API_HASH'])
    await client.connect()
    if not await client.is_user_authorized():
        print('Not authorized')
        return

    found = []
    for uname in USERNAMES:
        try:
            entity = await client.get_entity(uname)
            subs = getattr(entity, 'participants_count', None) or 0
            title = getattr(entity, 'title', '') or ''
            bc = getattr(entity, 'broadcast', False)
            if bc:
                found.append({'username': uname, 'title': title, 'subscribers': subs})
                print(f'  ✅ @{uname:30s} → {title[:60]:60s} подп: {subs}')
        except UsernameNotOccupiedError:
            pass
        except ChannelPrivateError:
            print(f'  🔒 @{uname:30s} → приватный')
        except FloodWaitError as e:
            print(f'  ⏳ flood wait {e.seconds}s')
            await asyncio.sleep(min(e.seconds, 3))
        except Exception as e:
            pass
        await asyncio.sleep(1.5)

    print(f'\nНайдено каналов: {len(found)}')
    for f in found:
        print(f'  @{f["username"]} | {f["subscribers"]:>6} | {f["title"]}')

    await client.disconnect()

asyncio.run(main())
