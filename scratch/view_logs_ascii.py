import paramiko

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASSWORD)
        print("Bot logs (ASCII only):")
        stdin, stdout, stderr = client.exec_command(f"cd {PROJECT_DIR} && docker compose logs --tail=30 bot")
        out = stdout.read().decode('utf-8', errors='ignore')
        # Clean any complex unicode characters to avoid windows printing crashes
        clean_out = "".join(c if ord(c) < 128 else "?" for c in out)
        print(clean_out)
        client.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
