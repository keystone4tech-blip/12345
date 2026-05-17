import paramiko

script_to_run = """
import asyncio
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.database.models import SystemSettings
import urllib.request
import json

async def main():
    try:
        async with AsyncSessionLocal() as db:
            query = select(SystemSettings).where(SystemSettings.key == 'bot_token')
            result = await db.execute(query)
            token_setting = result.scalar_one_or_none()
            if token_setting:
                token = token_setting.value
                req = urllib.request.urlopen(f'https://api.telegram.org/bot{token}/getMe')
                bot_info = json.loads(req.read())
                print("BOT_USERNAME=" + bot_info['result']['username'])
            else:
                print("No bot_token found in SystemSettings")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    sftp = client.open_sftp()
    with sftp.file('/tmp/get_bot.py', 'w') as f:
        f.write(script_to_run)
    sftp.close()
    
    cmd = "cd /opt/mozhnovpn && docker compose cp /tmp/get_bot.py bot:/app/get_bot.py && docker compose exec -T bot python /app/get_bot.py"
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode())
    print(stderr.read().decode())
    client.close()
except Exception as e:
    print(f"Error: {e}")
