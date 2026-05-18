import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

# IDs of the users to modify
user_ids = [17, 24, 45, 46]
admin_user_id = 1 # ID of the Admin/Superadmin bot account as the referrer

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("Connecting to 31.13.208.149...")
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    
    # SQL Transaction:
    # 1. Remove admin roles assigned to these users in user_roles
    # 2. Update referred_by_id to the admin user (ID 1)
    sql_query = f"""
    BEGIN;
    
    DELETE FROM user_roles 
    WHERE user_id IN ({','.join(map(str, user_ids))});
    
    UPDATE users 
    SET referred_by_id = {admin_user_id} 
    WHERE id IN ({','.join(map(str, user_ids))});
    
    COMMIT;
    """
    
    print("Executing database changes (removing admin roles, assigning admin as referrer)...")
    cmd = f"cd /opt/mozhnovpn && docker compose exec -T postgres psql -U postgres -d jarvis_vpn -c \"{sql_query}\""
    
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
        print("\nSuccessfully updated users' referrals and removed admin roles!")
             
except Exception as e:
    print(f"An error occurred: {e}")
