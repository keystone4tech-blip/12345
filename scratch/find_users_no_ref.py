import paramiko
import csv
import io
import sys

# Force stdout to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# SQL-запрос для получения всех пользователей
sql_query = "SELECT u.id, u.telegram_id, u.username, u.first_name, u.last_name, u.referral_code, u.referred_by_id, COALESCE(string_agg(ar.name, ', '), '') as roles FROM users u LEFT JOIN user_roles ur ON u.id = ur.user_id AND ur.is_active = TRUE LEFT JOIN admin_roles ar ON ur.role_id = ar.id GROUP BY u.id ORDER BY u.id ASC"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    
    # Run the copy command
    cmd = f"cd /opt/mozhnovpn && docker compose exec -T postgres psql -U postgres -d jarvis_vpn -c \"copy ({sql_query}) to stdout with csv header delimiter ','\""
    
    stdin, stdout, stderr = client.exec_command(cmd)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    client.close()
    
    if not out.strip():
        print("No output received from the server.")
        exit(1)
        
    f = io.StringIO(out.strip())
    reader = csv.DictReader(f)
    users = list(reader)
    
    print("\n| ID | Telegram ID | Username | Name | Ref Code | Referred By ID | Roles |")
    print("|---|---|---|---|---|---|---|")
    for u in users:
        username = u.get('username') or 'None'
        if username.strip() == '':
            username = 'None'
            
        first_name = u.get('first_name') or ''
        last_name = u.get('last_name') or ''
        name = f"{first_name} {last_name}".strip() or 'None'
        ref_code = u.get('referral_code') or 'None'
        referred_by = u.get('referred_by_id') or 'None'
        roles = u.get('roles') or 'None'
        
        print(f"| {u['id']} | {u['telegram_id']} | {username} | {name} | {ref_code} | {referred_by} | {roles} |")
             
except Exception as e:
    print(f"An error occurred: {e}")
