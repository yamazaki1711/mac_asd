import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')
from telethon import TelegramClient

API_ID = int(os.environ.get('TELEGRAM_API_ID', '0'))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
PHONE = os.environ.get('TELEGRAM_PHONE', '')
HASH_FILE = "/tmp/tg_auth_hash.txt"
CODE_FILE = "/tmp/tg_auth_code.txt"
RESULT_FILE = "/tmp/tg_auth_result.txt"

async def main():
    if not API_ID or not API_HASH:
        print("ERROR: TELEGRAM_API_ID or TELEGRAM_API_HASH not set in .env")
        return

    client = TelegramClient('/home/oleg/MAC_ASD/telegram_session', API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        with open(RESULT_FILE, 'w') as f:
            f.write(f"ALREADY_AUTHED:{me.first_name}:@{me.username}:{me.id}")
        await client.disconnect()
        return

    if not PHONE:
        print("ERROR: TELEGRAM_PHONE not set in .env")
        await client.disconnect()
        return

    sent = await client.send_code_request(PHONE)
    with open(HASH_FILE, 'w') as f:
        f.write(sent.phone_code_hash)
    print(f"READY:{sent.phone_code_hash}")

    # Wait for code file
    for _ in range(120):
        if os.path.exists(CODE_FILE):
            with open(CODE_FILE) as f:
                code = f.read().strip()
            os.remove(CODE_FILE)
            result = await client.sign_in(PHONE, code, phone_code_hash=sent.phone_code_hash)
            me = await client.get_me()
            msg = f"SUCCESS:{me.first_name}:@{me.username}:{me.id}"
            with open(RESULT_FILE, 'w') as f:
                f.write(msg)
            print(msg)
            break
        await asyncio.sleep(1)
    else:
        with open(RESULT_FILE, 'w') as f:
            f.write("TIMEOUT")
        print("TIMEOUT")

    await client.disconnect()

asyncio.run(main())
