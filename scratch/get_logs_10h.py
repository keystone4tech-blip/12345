
import paramiko
import sys

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    
    # Запрашиваем логи за последние 10 часов
    stdin, stdout, stderr = client.exec_command("docker logs --since 10h remnawave_bot")
    logs = stdout.read().decode("utf-8", errors="replace")
    errs = stderr.read().decode("utf-8", errors="replace")
    
    with open("bot_logs_10h.txt", "w", encoding="utf-8") as f:
        f.write(logs)
        if errs:
            f.write("\n\nSTDERR:\n")
            f.write(errs)
    
    print("Логи за 10 часов сохранены в bot_logs_10h.txt")
    
    client.close()

if __name__ == "__main__":
    main()
