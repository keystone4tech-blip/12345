import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    stdin, stdout, stderr = client.exec_command('cd /opt/mozhnovpn && docker compose ps --format json')
    output = stdout.read().decode().strip()
    
    if '"Service": "bot"' in output:
        print("YES")
    else:
        print("NO")
        
    client.close()
except Exception as e:
    print(f"Error: {e}")
