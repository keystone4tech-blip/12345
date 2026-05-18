import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

# IDs of the users to receive the Admin role
user_ids = [17, 24, 45, 46]
admin_role_id = 2 # Role "Admin" as default

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("Connecting to 31.13.208.149...")
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    
    # We will build SQL commands to assign the role in an idempotent way
    sql_commands = []
    
    # 1. Check/Insert role assignment
    for user_id in user_ids:
        # PostgreSQL UPSERT using ON CONFLICT to avoid violating uq_user_role unique constraint
        cmd = f"""
        INSERT INTO user_roles (user_id, role_id, is_active, assigned_at)
        VALUES ({user_id}, {admin_role_id}, TRUE, NOW())
        ON CONFLICT ON CONSTRAINT uq_user_role 
        DO UPDATE SET is_active = TRUE, assigned_at = NOW();
        """
        sql_commands.append(cmd.strip())
        
    full_sql = " ".join(sql_commands)
    
    print("Executing role assignment in PostgreSQL database...")
    cmd = f"cd /opt/mozhnovpn && docker compose exec -T postgres psql -U postgres -d jarvis_vpn -c \"{full_sql}\""
    
    stdin, stdout, stderr = client.exec_command(cmd)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    client.close()
    
    if err:
        print("SQL Error occurred:")
        print(err)
    else:
        print("SQL Output:")
        print(out)
        print("\nSuccessfully assigned 'Admin' (ID 2) role to users: 17, 24, 45, 46!")
             
except Exception as e:
    print(f"An error occurred: {e}")
