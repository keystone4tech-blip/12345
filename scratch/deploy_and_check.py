import paramiko
import time

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

def run_ssh_command(client, cmd):
    print(f"\nExecuting: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    
    # Wait for the command to finish
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
        print("Successfully connected to the server!")
        
        # 1. Pull the latest changes
        run_ssh_command(client, f"cd {PROJECT_DIR} && git pull")
        
        # 2. Rebuild and restart containers
        print("\nRebuilding and restarting docker containers...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose up -d --build")
        
        # 3. Wait a few seconds for services to initialize
        print("\nWaiting 5 seconds for services to spin up...")
        time.sleep(5)
        
        # 4. Check docker compose status
        print("\nChecking container status...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose ps")
        
        # 5. Check bot logs for errors
        print("\nChecking bot logs for errors...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose logs --tail=100 bot")
        
        # 6. Check cabinet logs for errors
        print("\nChecking cabinet logs...")
        run_ssh_command(client, f"cd {PROJECT_DIR} && docker compose logs --tail=50 cabinet")
        
        client.close()
        print("\nDeployment and validation check complete!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
