import paramiko

HOST = "31.13.208.149"
USER = "root"
PASSWORD = "SuperNatural24!"
PROJECT_DIR = "/opt/mozhnovpn"

def run_cmd(client, cmd):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print("STDOUT:", out.strip())
    if err: print("STDERR:", err.strip())

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(HOST, username=USER, password=PASSWORD)
    print("Connected to server")
    
    # Update .env
    sed_cmd = f"sed -i 's/Jarvis_VPN_Robot/MozhnoVPN_Robot/g' {PROJECT_DIR}/.env && sed -i 's/Jarvis VPN Cabinet/MozhnoVPN Cabinet/g' {PROJECT_DIR}/.env"
    run_cmd(client, sed_cmd)
    
    # Rebuild cabinet
    rebuild_cmd = f"cd {PROJECT_DIR} && docker compose build --no-cache cabinet && docker compose up -d cabinet"
    
    # Use pty to get real-time output for docker compose
    print(f"\n>>> {rebuild_cmd}")
    stdin, stdout, stderr = client.exec_command(rebuild_cmd, get_pty=True)
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            print(stdout.channel.recv(1024).decode("utf-8", errors="replace"), end="")
    print(stdout.read().decode("utf-8", errors="replace"))
    
    client.close()
    print("Environment variables updated and frontend rebuilt!")
except Exception as e:
    print(f"Error: {e}")
