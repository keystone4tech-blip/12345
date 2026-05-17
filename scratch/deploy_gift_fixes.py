import paramiko
import os

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

LOCAL_GIFT_PY = r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\app\cabinet\routes\gift.py"
LOCAL_GIFT_TSX = r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\cabinet\src\pages\GiftSubscription.tsx"

REMOTE_GIFT_PY = f"{PROJECT_DIR}/bot/app/cabinet/routes/gift.py"
REMOTE_GIFT_TSX = f"{PROJECT_DIR}/cabinet/src/pages/GiftSubscription.tsx"
REMOTE_CABINET_ENV = f"{PROJECT_DIR}/cabinet/.env"

def run_cmd(client, cmd):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if out: print("STDOUT:", out.strip())
    if err: print("STDERR:", err.strip())

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(HOST, username=USER, password=PASSWORD)
    print("Connected to server via SSH")
    
    # 1. Update cabinet/.env
    sed_cmd = f"sed -i 's/Jarvis_VPN_Robot/MozhnoVPN_Robot/g' {REMOTE_CABINET_ENV} && sed -i 's/Jarvis VPN Cabinet/MozhnoVPN Cabinet/g' {REMOTE_CABINET_ENV}"
    run_cmd(client, sed_cmd)
    
    # 2. Upload files via SFTP
    sftp = client.open_sftp()
    print(f"Uploading {LOCAL_GIFT_PY} -> {REMOTE_GIFT_PY}")
    sftp.put(LOCAL_GIFT_PY, REMOTE_GIFT_PY)
    
    print(f"Uploading {LOCAL_GIFT_TSX} -> {REMOTE_GIFT_TSX}")
    sftp.put(LOCAL_GIFT_TSX, REMOTE_GIFT_TSX)
    sftp.close()
    
    # 3. Rebuild cabinet
    rebuild_cmd = f"cd {PROJECT_DIR} && docker compose build --no-cache cabinet && docker compose up -d cabinet"
    print(f"\n>>> {rebuild_cmd}")
    stdin, stdout, stderr = client.exec_command(rebuild_cmd, get_pty=True)
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            print(stdout.channel.recv(1024).decode("utf-8", errors="replace"), end="")
    print(stdout.read().decode("utf-8", errors="replace"))
    
    # 4. Restart bot
    restart_bot_cmd = f"cd {PROJECT_DIR} && docker compose restart bot"
    run_cmd(client, restart_bot_cmd)
    
    client.close()
    print("\nAll gift fixes deployed and services updated/restarted successfully!")
except Exception as e:
    print(f"Error: {e}")
