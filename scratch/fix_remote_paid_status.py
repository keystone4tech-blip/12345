import paramiko

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

script_to_run = """
import asyncio
import sys
sys.path.insert(0, '/app')
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.database.models import User, Subscription

async def main():
    try:
        async with AsyncSessionLocal() as db:
            query = select(User).join(Subscription).where(
                User.has_had_paid_subscription == False,
                Subscription.is_trial == False,
                Subscription.status == 'active'
            )
            result = await db.execute(query)
            users = result.scalars().all()
            print(f'Found {len(users)} users to fix.')
            for user in users:
                user.has_had_paid_subscription = True
            await db.commit()
            print('Done fixing users.')
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(HOST, username=USER, password=PASSWORD)
    print("Connected to server")
    
    # Write the script to a temporary file on the server
    sftp = client.open_sftp()
    with sftp.file('/tmp/fix_users.py', 'w') as f:
        f.write(script_to_run)
    sftp.close()
    
    cmd = f"cd {PROJECT_DIR} && docker compose exec -T bot python /app/fix_users.py"
    print(f"\n>>> {cmd}")
    
    # We copy the script to the volume or just pipe it
    # Even better, copy to container using docker cp with compose
    copy_cmd = f"cd {PROJECT_DIR} && docker compose cp /tmp/fix_users.py bot:/app/fix_users.py"
    stdin, stdout, stderr = client.exec_command(copy_cmd)
    print("Copy result:", stdout.read().decode())
    print("Copy error:", stderr.read().decode())
    
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(out)
    if err:
        print("ERRORS:", err)
        
    client.close()
    print("\nFix complete!")
except Exception as e:
    print(f"Error: {e}")
