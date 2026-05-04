import paramiko

def update_server():
    hostname = '31.13.208.149'
    username = 'root'
    password = 'SuperNatural24!'

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname, username=username, password=password)
        
        commands = [
            "cd /opt/mozhnovpn && git pull",
            "cd /opt/mozhnovpn/bot && docker compose restart bot",
            "cd /opt/mozhnovpn/cabinet && docker compose build --no-cache cabinet && docker compose up -d cabinet",
            "cd /opt/mozhnovpn/bot && docker compose exec bot python migrate_referral_codes.py"
        ]
        
        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            if out: print(out)
            if err: print(err)
            
    finally:
        client.close()

if __name__ == "__main__":
    update_server()
