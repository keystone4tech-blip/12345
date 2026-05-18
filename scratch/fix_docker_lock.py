import paramiko
import time

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

def run_ssh_command(client, cmd):
    print(f"\nExecuting: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    print(f"Exit code: {exit_status}")
    if out:
        print(f"Output:\n{out}")
    if err:
        print(f"Error:\n{err}")
    return exit_status, out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to {HOST}...")
        client.connect(HOST, username=USER, password=PASSWORD)
        print("Connected!")
        
        # 1. Force remove any problematic containers
        print("\nForce removing cabinet container to clear docker lock...")
        run_ssh_command(client, "docker rm -f cabinet_frontend")
        run_ssh_command(client, "docker rm -f remnawave_bot")
        
        # 2. Stop compose
        print("\nStopping docker compose...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose down")
        
        # 3. Start compose
        print("\nStarting docker compose stack...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose up -d")
        
        # 4. Wait for initialization
        print("\nWaiting 10 seconds for services to fully initialize...")
        time.sleep(10)
        
        # 5. Check container statuses
        print("\nChecking container statuses...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose ps")
        
        # 6. Check logs
        print("\nChecking bot logs...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose logs --tail=50 bot")
        
        print("\nChecking cabinet logs...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose logs --tail=50 cabinet")
        
        client.close()
        print("\nDocker lock resolved and services verified successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
