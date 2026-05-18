import paramiko
import csv
import io
import sys

sys.stdout.reconfigure(encoding='utf-8')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    
    # Query admin_roles table
    sql_query = "SELECT id, name, level, description FROM admin_roles ORDER BY level DESC"
    cmd = f"cd /opt/mozhnovpn && docker compose exec -T postgres psql -U postgres -d jarvis_vpn -c \"copy ({sql_query}) to stdout with csv header delimiter ','\""
    
    stdin, stdout, stderr = client.exec_command(cmd)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    client.close()
    
    if err:
        print("SQL Error:", err)
        exit(1)
        
    f = io.StringIO(out.strip())
    reader = csv.DictReader(f)
    roles = list(reader)
    
    print("\n=== AVAILABLE ADMIN ROLES ===")
    for r in roles:
        print(f"ID: {r['id']} | Name: {r['name']} | Level: {r['level']} | Description: {r['description']}")
             
except Exception as e:
    print(f"An error occurred: {e}")
