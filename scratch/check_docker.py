import time
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    print("Connected to server. Waiting for bot container...")
    
    for _ in range(30):
        stdin, stdout, stderr = client.exec_command('cd /opt/mozhnovpn && docker compose ps --format json')
        output = stdout.read().decode().strip()
        if '"Service": "bot"' in output:
            print("Bot is up!")
            print(output)
            break
        print("Waiting...")
        time.sleep(10)
    
    client.close()
except Exception as e:
    print(f"Error: {e}")
