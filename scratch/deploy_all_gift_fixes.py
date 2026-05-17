import paramiko
import os

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

FILES_TO_UPLOAD = {
    r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\app\cabinet\routes\gift.py": f"{PROJECT_DIR}/bot/app/cabinet/routes/gift.py",
    r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\app\services\gift_service.py": f"{PROJECT_DIR}/bot/app/services/gift_service.py",
    r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\app\handlers\start.py": f"{PROJECT_DIR}/bot/app/handlers/start.py",
    r"c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\cabinet\src\pages\GiftSubscription.tsx": f"{PROJECT_DIR}/cabinet/src/pages/GiftSubscription.tsx",
}

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
    
    # 1. Upload files via SFTP
    sftp = client.open_sftp()
    for local, remote in FILES_TO_UPLOAD.items():
        print(f"Uploading {local} -> {remote}")
        sftp.put(local, remote)
    sftp.close()
    print("Files uploaded successfully!")
    
    # 2. Rebuild bot service (since python source files changed)
    rebuild_bot_cmd = f"cd {PROJECT_DIR} && docker compose build --no-cache bot && docker compose up -d bot"
    print(f"\n>>> {rebuild_bot_cmd}")
    stdin, stdout, stderr = client.exec_command(rebuild_bot_cmd, get_pty=True)
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            print(stdout.channel.recv(1024).decode("utf-8", errors="replace"), end="")
    print(stdout.read().decode("utf-8", errors="replace"))

    # 3. Rebuild cabinet service (since frontend React source files changed)
    rebuild_cabinet_cmd = f"cd {PROJECT_DIR} && docker compose build --no-cache cabinet && docker compose up -d cabinet"
    print(f"\n>>> {rebuild_cabinet_cmd}")
    stdin, stdout, stderr = client.exec_command(rebuild_cabinet_cmd, get_pty=True)
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            print(stdout.channel.recv(1024).decode("utf-8", errors="replace"), end="")
    print(stdout.read().decode("utf-8", errors="replace"))
    
    client.close()
    print("\nAll gift fixes deployed and services rebuilt successfully!")
except Exception as e:
    print(f"Error: {e}")
