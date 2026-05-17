import paramiko

sql_query = "UPDATE users SET has_had_paid_subscription = TRUE FROM subscriptions WHERE users.id = subscriptions.user_id AND users.has_had_paid_subscription = FALSE AND subscriptions.is_trial = FALSE;"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect("31.13.208.149", username="root", password="SuperNatural24!")
    cmd = f"cd /opt/mozhnovpn && docker compose exec -T postgres psql -U postgres -d jarvis_vpn -c \"{sql_query}\""
    print(f"Running: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    
    out = stdout.read().decode()
    err = stderr.read().decode()
    
    print("STDOUT:", out)
    print("STDERR:", err)
    
    client.close()
    print("SQL execution complete!")
except Exception as e:
    print(f"Error: {e}")
