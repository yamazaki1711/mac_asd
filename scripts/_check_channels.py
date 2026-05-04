import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

PROCUREMENT = [
    'state_order', 'rbzakup', 'zakupki44fz', 'bottender1c',
    'zakupki_44_fz', 'praktikum44', 'sibirfedokrug', 'dalnevostokf',
    'zakupki44223275', 'kodeks_gmz',
]

async def main():
    client = TelegramClient('credentials/telethon_session',
                           int(os.environ['TELEGRAM_API_ID']),
                           os.environ['TELEGRAM_API_HASH'])
    await client.connect()

    for uname in PROCUREMENT:
        try:
            entity = await client.get_entity(uname)
            full = await client(GetFullChannelRequest(channel=entity))
            subs = getattr(full.full_chat, 'participants_count', 0) or 0
            about = (getattr(full.full_chat, 'about', '') or '')[:120]
            title = entity.title or ''
            print(f'@{uname:25s} | {subs:>7} | {title[:60]}')
            if about:
                print(f'  {"":27s}  {about}')
        except Exception as e:
            print(f'@{uname:25s} | ERROR: {e}')
        await asyncio.sleep(1.5)

    await client.disconnect()
asyncio.run(main())
