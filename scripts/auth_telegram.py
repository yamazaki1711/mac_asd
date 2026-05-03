import asyncio, os, time
from telethon import TelegramClient

API_ID = 30129715
API_HASH = "ffa9b125d9c4107c4a029ae7c84bc07f"
PHONE = "+79246884488"
HASH_FILE = "/tmp/tg_auth_hash.txt"
CODE_FILE = "/tmp/tg_auth_code.txt"
RESULT_FILE = "/tmp/tg_auth_result.txt"

async def main():
    client = TelegramClient('/home/oleg/MAC_ASD/telegram_session', API_ID, API_HASH)
    await client.connect()
    
    if await client.is_user_authorized():
        me = await client.get_me()
        with open(RESULT_FILE, 'w') as f:
            f.write(f"ALREADY_AUTHED:{me.first_name}:@{me.username}:{me.id}")
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
